# CI/CD Setup Guide

This guide explains the CI/CD pipeline added to the repository, and the
**one-time** GitHub-side configuration you have to do before the workflows
will all turn green.

## 1. Pipeline at a glance

```
┌─────────────────┐       ┌───────────────────────────────────────────────┐
│  Pull Request   │──────▶│  ci.yml  (.github/workflows/ci.yml)           │
│  push to main   │       │   ├─ backend (ruff + unit & integration pytest│
│  manual run     │       │   │            runs w/ JUnit artifacts, PG 17)│
└─────────────────┘       │   ├─ frontend (eslint + tsc + vitest + build) │
                          │   ├─ db-schema (apply sql/*.sql in order)     │
                          │   ├─ sonarcloud (quality gate)                │
                          │   ├─ sast-bandit (Bandit, BLOCKING)           │
                          │   └─ dependency-audit (pip-audit + npm audit, │
                          │      BLOCKING w/ triaged ignore list)         │
                          └────────────────┬──────────────────────────────┘
                                           │ on push to main
                                           ▼
                         ┌──────────────────────────────────────────────┐
                         │  build-images.yml                            │
                         │   ├─ build backend → ghcr.io/.../backend     │
                         │   ├─ build frontend → ghcr.io/.../frontend   │
                         │   └─ Trivy scan (HIGH / CRITICAL)            │
                         └──────────────────────────────────────────────┘
                                           │
                                           ▼
                                  [Manual deploy — not automated]
```

## 2. Files added to the repo

| Path | Role |
|---|---|
| `.github/workflows/ci.yml` | PR + push CI: lint, test, SonarCloud, dep audit |
| `.github/workflows/build-images.yml` | main / tag: docker build + push GHCR + Trivy (blocking on fixable HIGH/CRITICAL) |
| `.github/workflows/load-test.yml` | Locust load (20u/2min) + stress (100u/90s) phases, HTML/CSV report artifacts, p95 threshold gate |
| `.github/workflows/dast.yml` | OWASP ZAP baseline (SPA via nginx) + OpenAPI-driven API scan against the running stack; weekly rescan |
| `.zap/rules.tsv` | ZAP rule triage list (justified ignores) |
| `loadtest/locustfile.py` | Locust user scenarios (read-only endpoints) |
| `security/pip-audit-ignores.txt` | Triaged accepted-risk advisories (blocking otherwise) |
| `security/VULNERABILITY_ASSESSMENT.md` | Find → fix → rescan evidence chain (SAST/SCA/Trivy/DAST) |
| `security/COMPLIANCE.md` | Compliance-as-code mapping (SOC 2 controls, PDPA/GDPR) |
| `.github/pull_request_template.md` | PR description template |
| `.pre-commit-config.yaml` | Local pre-commit hooks (ruff, prettier, hygiene) |
| `sonar-project.properties` | SonarCloud project config |
| `docker-compose.yml` | One-command local stack (postgres + backend + frontend) |
| `backend/Dockerfile` | Backend image (python:3.11-slim, multi-stage) |
| `backend/.dockerignore` | Slim build context |
| `backend/pyproject.toml` | Ruff + pytest + coverage config |
| `backend/requirements-dev.txt` | Dev/CI extras (ruff, pytest, httpx, pip-audit) |
| `backend/tests/test_health.py` | Starter tests |
| `frontend/Dockerfile` | Frontend image (node build → nginx serve) |
| `frontend/nginx.conf` | SPA + `/api` reverse proxy |
| `frontend/.dockerignore` | Slim build context |
| `frontend/eslint.config.js` | ESLint 9 flat config (was missing) |
| `frontend/.prettierrc.json` | Prettier config |
| `frontend/vitest.config.ts` | Vitest + jsdom + v8 coverage |
| `frontend/src/test/setup.ts` | jest-dom matchers + cleanup |
| `frontend/src/__tests__/App.test.tsx` | Starter test |

## 3. One-time GitHub configuration

### 3.1 SonarCloud (required for the `sonarcloud` job)

1. Sign in at <https://sonarcloud.io> with GitHub.
2. Click *Analyze new project* → choose this repository.
3. Pick **GitHub Actions** as the analysis method.
4. Copy the generated `SONAR_TOKEN`.
5. In GitHub: **Settings → Secrets and variables → Actions → New repository
   secret** → name `SONAR_TOKEN`, value from step 4.
6. Open `sonar-project.properties` and replace the two `REPLACE_WITH_...`
   placeholders with the *organization* and *project key* shown in
   SonarCloud (formats look like `your-org` and `your-org_DBDesign`).
7. (Optional but recommended) Disable *Automatic Analysis* in SonarCloud
   project settings — it conflicts with CI-driven scans.

### 3.2 GitHub Container Registry (GHCR) — for `build-images.yml`

No secret to add: the workflow uses the built-in `GITHUB_TOKEN`. But you
must allow it to publish packages:

- **Settings → Actions → General → Workflow permissions** → tick
  *Read and write permissions*.
- After the first push, **Packages** tab → each new package → **Package
  settings → Manage Actions access** → grant the repo *Write*.
- (Optional) Mark the package as *public* if reviewers without GitHub
  accounts need to pull.

### 3.3 Branch protection on `main`

**Settings → Branches → Add branch protection rule** → pattern `main`:

- ☑ Require a pull request before merging
- ☑ Require status checks to pass before merging:
  - `Backend (lint + test)`
  - `Frontend (lint + test + build)`
  - `DB schema check`
  - `SonarCloud quality gate`
- ☑ Require branches to be up to date before merging
- ☑ Do not allow bypassing the above

### 3.4 Dependency updates

Dependabot was intentionally **not enabled** for this project (mid-development
noise outweighed the value). To bring it back later, drop a
`.github/dependabot.yml` describing pip / npm / actions / docker ecosystems.

## 4. Local developer onboarding

Once-per-clone:

```bash
# Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# Frontend
cd ../frontend
npm install

# Pre-commit (project root)
cd ..
pip install pre-commit
pre-commit install
```

Daily commands:

```bash
# Run backend tests
cd backend && pytest

# Lint & format backend
ruff check . && ruff format .

# Run frontend tests
cd frontend && npm test

# Lint & format frontend
npm run lint && npm run format

# Spin up the full stack locally
docker compose up -d
```

## 5. Reading CI failures

| Failing job | Where to look |
|---|---|
| `Backend (lint + test)` | Run output of `ruff check .` or `pytest`; coverage XML in artifacts |
| `Frontend (lint + test + build)` | Run output of `npm run lint` / `vitest`; `frontend-dist` artifact for built bundle |
| `DB schema check` | Logs of `psql -f sql/...` — usually a syntax error in a `.sql` file |
| `SonarCloud quality gate` | Click the *SonarCloud* check on the PR for the full report |
| `Dependency audit` | Currently `continue-on-error: true` — informational only |
| `Build & Publish` | Trivy SARIF appears in **Security → Code scanning** |

## 6. Image conventions

- Registry: `ghcr.io/<owner>/dbdesign-backend`, `ghcr.io/<owner>/dbdesign-frontend`
- Tags published on every `main` push:
  - `:sha-<short>` — immutable, reproducible
  - `:main` — latest from main
  - `:latest` — alias of latest main
- Tags published on `git tag vX.Y.Z`:
  - `:vX.Y.Z`, `:X.Y`, `:X.Y.Z`

Pull and run an image manually:

```bash
docker pull ghcr.io/<owner>/dbdesign-backend:latest
docker run --rm -p 8000:8000 \
  -e DATABASE_URL=postgresql+psycopg://postgres:postgres@host.docker.internal:5432/ecotea \
  ghcr.io/<owner>/dbdesign-backend:latest
```

## 7. Continuous Deployment — environment-ready

CD is implemented in `.github/workflows/deploy.yml` with an
**environment-ready** design: the full deploy path (immutable image tags,
health checks, smoke tests, auto-rollback, prod approval gate) runs and is
validated on every release, while the physical target stays pluggable.

```
main push ─▶ CI ─▶ Build & Publish ─▶ deploy-staging   (automatic)
tag v*    ─▶ CI ─▶ Build & Publish ─▶ deploy-production (approval gate*)
```

Each deploy job picks one of two modes, decided by whether the
`DEPLOY_HOST` secret exists:

| Mode | When | What happens |
|---|---|---|
| **Ephemeral** (default) | No server configured | The full stack (postgres + backend + frontend images from GHCR) is brought up **on the runner** via `deploy/deploy.sh`, health-checked and smoke-tested, then torn down. The entire deploy path is exercised at zero infrastructure cost. |
| **Server** | `DEPLOY_HOST` set | SSH to the host, `git checkout` the exact commit/tag, run the **same** `deploy/deploy.sh`. On health-check failure the script auto-rolls back to the last good tag. |

Shared pieces (identical in both modes):

- `deploy/docker-compose.deploy.yml` — pull-only stack; env isolation via
  compose project names (`strata-staging` / `strata-prod`) and distinct ports.
- `deploy/deploy.sh` — pull → up → poll `/api/health` + frontend → record
  last-good tag, or roll back to it and exit non-zero.
- Deploys always use **immutable tags** (`sha-<short>` from main builds,
  `vX.Y.Z` from releases) — never `latest` — so every deploy is reproducible
  and rollback is a one-liner.
- `workflow_dispatch` allows manually deploying any tag to either environment
  (also serves as the approval mechanism on plans without protected
  Environments*).

### Switching to a real server (zero code changes)

1. Provision a host with docker + compose; `git clone` the repo to
   `/opt/strata/repo`; `docker login ghcr.io` with a `read:packages` PAT.
2. Add repo secrets `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`
   (a dedicated deploy user restricted to the compose directory).
3. (Optional) In **Settings → Environments → production**, add *Required
   reviewers* for a manual approval gate. *Free on public repos; on private
   repos this needs GitHub Team — use `workflow_dispatch` as the gate instead.

Nothing else changes: same compose file, same script, same workflow.

## 8. What's intentionally **not** included

- **A permanent hosting target.** The project has no production owner yet;
  see §7 — the pipeline is validated end-to-end in ephemeral mode and a real
  server is a 3-secret configuration change, not a code change.
- **End-to-end tests.** Defer until business logic stabilises. (The CD smoke
  tests cover health, key API routes, and the nginx `/api` proxy.)
- **Self-hosted SonarQube / Jenkins / Nexus.** Hosted services keep ops to zero.
