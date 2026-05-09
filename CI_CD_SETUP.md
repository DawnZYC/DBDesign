# CI/CD Setup Guide

This guide explains the CI/CD pipeline added to the repository, and the
**one-time** GitHub-side configuration you have to do before the workflows
will all turn green.

## 1. Pipeline at a glance

```
┌─────────────────┐       ┌───────────────────────────────────────────────┐
│  Pull Request   │──────▶│  ci.yml  (.github/workflows/ci.yml)           │
│  push to main   │       │   ├─ backend (ruff + pytest + PG 17)          │
│  manual run     │       │   ├─ frontend (eslint + tsc + vitest + build) │
└─────────────────┘       │   ├─ db-schema (apply sql/*.sql in order)     │
                          │   ├─ sonarcloud (quality gate)                │
                          │   └─ dependency-audit (pip-audit + npm audit) │
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
| `.github/workflows/build-images.yml` | main / tag: docker build + push GHCR + Trivy |
| `.github/dependabot.yml` | Weekly dependency PRs (pip / npm / actions / docker) |
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

### 3.4 Dependabot

No setup required — committing `.github/dependabot.yml` enables it.
Optional: in **Settings → Code security**, enable *Dependabot alerts* and
*Dependabot security updates* to also get CVE-only PRs.

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

## 7. What's intentionally **not** included

- **Continuous Deployment.** The project is mid-development; auto-deploy
  is deferred until a real staging/prod environment exists. When ready,
  add `.github/workflows/deploy.yml` that triggers on `push: main` (→ staging)
  and `tag v*` (→ prod), and either SSH-pulls the GHCR image or invokes
  Cloud Run / ECS.
- **End-to-end tests.** Defer until business logic stabilises.
- **Self-hosted SonarQube / Jenkins / Nexus.** Hosted services keep ops to zero.
