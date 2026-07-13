#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Deploy (or validate) one Strata environment from prebuilt GHCR images.
#
# The SAME script runs in two places:
#   * CI runner (ephemeral validation) — proves the pipeline end-to-end
#   * a real server over SSH           — identical command, zero code changes
#
# Behaviour:
#   1. Remember the currently-running image tag as the rollback candidate.
#   2. compose pull + up -d with the requested images.
#   3. Poll backend /api/health and frontend / until healthy (or timeout).
#   4. Success  -> persist the new tag as "last good".
#      Failure  -> if a last-good tag exists, redeploy it (rollback), exit 1.
#
# Usage:
#   IMAGE_TAG=sha-abc1234 ./deploy.sh staging
#   IMAGE_TAG=v1.0.0      ./deploy.sh prod
#
# Optional env:
#   REGISTRY_NS    image namespace   (default ghcr.io/dawnzyc/dbdesign)
#   BACKEND_PORT   host port backend (default: staging 8000, prod 8001)
#   FRONTEND_PORT  host port frontend(default: staging 5173, prod 8080)
#   HEALTH_TIMEOUT seconds to wait   (default 180)
# ---------------------------------------------------------------------------
set -euo pipefail

ENV_NAME="${1:?usage: IMAGE_TAG=<tag> deploy.sh <staging|prod>}"
IMAGE_TAG="${IMAGE_TAG:?IMAGE_TAG is required (immutable sha-<short> or vX.Y.Z)}"
REGISTRY_NS="${REGISTRY_NS:-ghcr.io/dawnzyc/dbdesign}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-180}"

case "$ENV_NAME" in
  staging) BACKEND_PORT="${BACKEND_PORT:-8000}"; FRONTEND_PORT="${FRONTEND_PORT:-5173}" ;;
  prod)    BACKEND_PORT="${BACKEND_PORT:-8001}"; FRONTEND_PORT="${FRONTEND_PORT:-8080}" ;;
  *) echo "unknown environment: $ENV_NAME (want staging|prod)"; exit 2 ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.deploy.yml"
PROJECT="strata-$ENV_NAME"
STATE_FILE="$SCRIPT_DIR/.last_good_$ENV_NAME"   # survives between deploys on a server

export BACKEND_PORT FRONTEND_PORT

compose() {
  BACKEND_IMAGE="$REGISTRY_NS-backend:$1" \
  FRONTEND_IMAGE="$REGISTRY_NS-frontend:$1" \
  docker compose -p "$PROJECT" -f "$COMPOSE_FILE" "${@:2}"
}

wait_healthy() {
  local deadline=$((SECONDS + HEALTH_TIMEOUT))
  echo "==> Waiting for health (timeout ${HEALTH_TIMEOUT}s)..."
  until curl -fsS "http://localhost:$BACKEND_PORT/api/health" >/dev/null 2>&1 \
     && curl -fsS "http://localhost:$FRONTEND_PORT/" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      echo "!! Health check timed out."
      return 1
    fi
    sleep 5
  done
  echo "==> Healthy: backend :$BACKEND_PORT, frontend :$FRONTEND_PORT"
}

LAST_GOOD=""
[[ -f "$STATE_FILE" ]] && LAST_GOOD="$(cat "$STATE_FILE")"

echo "==> Deploying $PROJECT with tag '$IMAGE_TAG' (last good: '${LAST_GOOD:-none}')"
compose "$IMAGE_TAG" pull --quiet
compose "$IMAGE_TAG" up -d

if wait_healthy; then
  echo "$IMAGE_TAG" > "$STATE_FILE"
  echo "==> Deploy OK. '$IMAGE_TAG' recorded as last good."
  exit 0
fi

echo "!! Deploy of '$IMAGE_TAG' failed health check."
compose "$IMAGE_TAG" logs --tail 50 backend || true

if [[ -n "$LAST_GOOD" && "$LAST_GOOD" != "$IMAGE_TAG" ]]; then
  echo "==> Rolling back to '$LAST_GOOD'..."
  compose "$LAST_GOOD" up -d
  if wait_healthy; then
    echo "==> Rollback to '$LAST_GOOD' succeeded. Marking run as FAILED anyway."
  else
    echo "!! Rollback ALSO failed — manual intervention required."
  fi
fi
exit 1
