# DevSecOps Video — Final Recording Script (10 min)

For `TeamXX- Technical Assessment - DevSecOps.mp4`. Covers rubric a.i–e.
English narration, one screen at a time. Runs to **9:55**. c.i (SAST resolution)
is intentionally not a segment — Bandit is clean; the resolution story is told
through the Trivy loop instead.

**Legend:** **OPEN** = what's on screen · **DO** = clicks/commands · **SAY** =
narration · **SHOW** = the exact evidence a grader must see on screen.

---

## Prep (before recording — must exist)

- [ ] Green **CI** run on `main` (6 jobs) — with the Artifacts panel populated
- [ ] Green **Build & Publish Images** run + the earlier **failed** Trivy run still in history
- [ ] Green **Load & Stress** run with `locust-reports`
- [ ] **DAST #5** (before-fix, has findings) and **DAST #6** (after-fix, clean) both visible
- [ ] Local stack up (`docker compose up -d`), backend container name noted
- [ ] Pre-downloaded & unzipped: Locust HTML, bandit report, **both** ZAP reports (before + after)
- [ ] `terraform` installed locally so you can run `terraform plan` on camera (optional but strong)
- [ ] Tabs open in order; editor ready with: `security/VULNERABILITY_ASSESSMENT.md`,
      `security/.trivyignore`, `security/COMPLIANCE.md`, `.zap/rules.tsv`,
      `frontend/security_headers.conf`, `backend/Dockerfile`, `deploy/terraform/main.tf`
- [ ] Screen hygiene: 16pt+ terminal, 110–125% zoom, DND on, **no secrets tab**

---

## 0:00 – 0:35 · Opening

**OPEN:** `README.md` top / architecture.

**SAY:** "This is the DevSecOps walkthrough for Strata, a multi-agent energy-model
analytics platform — FastAPI, React, Postgres. I'll follow a change from commit to
deployed container, and stop at each security gate. Four blocks: the CI/CD pipeline
and its test evidence, container management, vulnerability resolution with rescans,
and compliance as code."

---

## 0:35 – 1:25 · a.i Pipelines and tools

**OPEN:** `.github/workflows/` directory listing → then `CI_CD_SETUP.md` §1.

**DO:** point at the five workflow files. Open `ci.yml`, scroll to a `permissions:` block.

**SAY:** "Five pipelines. `ci.yml` runs lint, tests, quality and security scans;
`build-images.yml` builds and Trivy-scans images; `dast.yml` runs OWASP ZAP;
`load-test.yml` runs Locust; `deploy.yml` ships to staging and production. Each is
least-privilege — read-only by default, write only where it's needed. Branch
protection on `main` makes CI and the image build the merge gate."

**SHOW:** the five `.yml` filenames; one `permissions:` block.

---

## 1:25 – 2:35 · a.ii + a.iii Unit & integration testing (result artifacts)

**OPEN:** the green **CI** run → expand `Backend (lint + test)`.

**DO:** scroll so `Unit tests` and `Integration tests (API + e2e)` steps are visible.
Then scroll to the **Artifacts** panel at the bottom of the run.

**SAY:** "Unit tests and integration tests run as separate steps. Integration tests
exercise the real API routers and an end-to-end import against Postgres — not mocks.
Both emit JUnit XML, uploaded as result artifacts alongside coverage."

**DO:** open a pre-downloaded coverage HTML (or the SonarCloud dashboard) for ~2 s;
flash a JUnit XML.

**SHOW (evidence):** the Artifacts panel listing `backend-test-results`,
`backend-coverage`, `frontend-test-results`, `frontend-coverage`, `frontend-dist`;
plus one opened report.

---

## 2:35 – 3:10 · a.iv Load and stress testing (result artifacts)

**OPEN:** `load-test.yml` (the two phase steps) → the Locust **HTML** report.

**SAY:** "Two phases: a load test at 20 users for two minutes, then a stress test at
100 users past expected capacity. The `Enforce performance thresholds` step fails the
job on p95-latency or error-rate regression — so it's a gate, not just a report."

**SHOW (evidence):** the two phase steps; the threshold step; the Locust HTML charts;
the `locust-reports` artifact name.

---

## 3:10 – 3:45 · a.v SAST (tool and result artifacts)

**OPEN:** CI run → `SAST (Bandit)` job → `bandit-reports` artifact → SonarCloud dashboard.

**SAY:** "Static analysis is Bandit across the backend, running blocking in CI, with
the report as an artifact. SonarCloud adds the quality gate — coverage, code smells,
and security hotspots. Bandit currently reports zero findings, so the codebase is
clean at the SAST layer."

**SHOW (evidence):** the Bandit step output; `bandit-reports` artifact; SonarCloud
quality-gate panel.

---

## 3:45 – 4:20 · a.vi DAST (tool and result artifacts)

**OPEN:** `dast.yml` → `.zap/rules.tsv` → one ZAP HTML report.

**SAY:** "Dynamic analysis is OWASP ZAP against the running full stack, brought up with
the same compose file we deploy. Two scans: a baseline passive scan of the SPA through
nginx, and an OpenAPI-driven API scan of the backend. Reports upload as artifacts;
`.zap/rules.tsv` is the triage log."

**SHOW (evidence):** the two ZAP scan steps; `rules.tsv`; a ZAP HTML report. (The
resolution loop comes later at 6:40 — here just establish the tool + artifacts.)

---

## 4:20 – 5:15 · b.i / b.iii / b.iv Container management (LIVE)

**OPEN:** `backend/Dockerfile` briefly → GHCR packages page → local terminal.

**SAY (build/publish):** "Multi-stage Dockerfile — a builder stage installs into an
isolated venv, the runtime carries only that venv and app code, runs as a non-root
user, with tini and a baked-in HEALTHCHECK. Images publish to GHCR tagged by commit
SHA and semver; deploys pin the immutable digest."

**DO (live terminal):**

```bash
docker compose ps
docker inspect --format '{{.State.Health.Status}}' <backend-container>   # your real name
docker compose exec backend python -c "from app.main import app; print(len(app.routes), 'routes')"
docker compose logs -f backend --tail 20
```

While `logs -f` streams, in a second pane: `curl -s localhost:8000/api/health` — let
the request appear in the log stream.

**SHOW (evidence):** GHCR tag list (`sha-…`, `latest`); the live `ps`/`inspect`/`exec`
output; a request landing in `logs -f` in real time.

---

## 5:15 – 6:40 · b.ii Image security + fix→rescan loop (Trivy) — CENTREPIECE

**OPEN, in order:** `build-images.yml` Trivy steps → the **failed** run's findings
table → `security/.trivyignore` → `VULNERABILITY_ASSESSMENT.md` §4 → the **green** run
→ Security tab SARIF.

**SAY:** "Trivy scans every image twice — a non-blocking table for readability, and a
blocking scan whose exit code gates the build. Turning that gate on took three rounds.
Round one: thirteen HIGH on the backend, triaged three ways — fixed the vulnerable
setuptools vendoring, accepted the starlette and langchain CVEs whose only fix is a
breaking major, and accepted the transformers CVEs that need attacker-supplied models.
Round two: still red — two transformers CVEs from the same batch had been missed, so I
upgraded transformers 4.46 to 4.48, a real fix, not an ignore. Round three: still red
with zero HIGH left — the gate itself was scanning all severities because of a
`trivy-action` flag, fixed with `limit-severities-for-sarif`. Now it's green."

**SHOW (evidence):** the failed run's HIGH findings; `.trivyignore` with justifications;
§4's three-round write-up; the green run; SARIF history in the Security tab.

---

## 6:40 – 7:55 · c.ii DAST resolution and rescan — CENTREPIECE (NEW)

**OPEN, in order:** `VULNERABILITY_ASSESSMENT.md` §5 (before table) → the **before** ZAP
report (DAST #5) → `frontend/security_headers.conf` + `backend/app/main.py` middleware
→ the **after** ZAP report (DAST #6) → `.zap/rules.tsv` → `dast.yml` `fail_action: true`.

**SAY:** "Same find-fix-rescan discipline for DAST. The first ZAP run flagged two
Medium findings on the frontend — no Content-Security-Policy and no anti-clickjacking
header — plus a set of missing security headers on the API. Zero High. I fixed them:
security headers in nginx for the SPA, and a headers middleware in FastAPI for direct
API access. The rescan — this run here — shows the frontend Mediums and the backend
header findings gone. The CSP I added introduced one residual about inline styles,
which I accept in `rules.tsv` because the charting library needs it. Everything
remaining is either fixed or a justified ignore — so I flipped ZAP to blocking. The
DAST gate is now real."

**SHOW (evidence):** §5 before/after tables side by side; before-report alert summary
(2 Medium, 7 Low) vs after-report (0 Medium untriaged); the `security_headers.conf`
diff; `rules.tsv` justifications; `fail_action: true` in `dast.yml`.

---

## 7:55 – 9:00 · d.i Infrastructure-as-Code + d.ii Audit trails

**OPEN:** `deploy/terraform/` tree → `main.tf` → `github-policy/main.tf` → terminal for
`terraform plan` (optional) → then `COMPLIANCE.md` control table + `git log --oneline`.

**SAY (IaC):** "Infrastructure is code in two Terraform modules. The runtime module uses
the Docker provider to declare the same network, volumes and three containers we deploy
— but state-tracked, so `terraform plan` previews changes before they happen. The second
module is policy-as-code: it codifies the branch-protection rules and the production
environment's required reviewers with the GitHub provider — turning governance controls
from clicked-in settings into reviewable code."

**DO (optional, strong):** `cd deploy/terraform && terraform plan` — show the plan output.

**SAY (audit trails):** "And every control in the compliance mapping points at a
versioned artifact — workflows, compose files, Terraform, the deploy script — so the Git
history is the audit trail. Control 12, right here."

**SHOW (evidence):** `main.tf` resources; `github-policy/main.tf` branch protection +
environments; `terraform plan` output if run; `COMPLIANCE.md` control table; `git log`.

---

## 9:00 – 9:35 · e Specific regulatory framework

**OPEN:** `COMPLIANCE.md` top section + framework bullets + the personal-data inventory.

**SAY:** "The framework choice is deliberate. SOC 2 Trust Services Criteria as the
control vocabulary for the engineering process, PDPA as the governing law, GDPR as the
reference framework — and HIPAA explicitly out of scope, because the system holds
energy-model technical data, no health data. The personal-data inventory shows what's
held today and what obligations activate if user accounts are added."

**SHOW (evidence):** the framework rationale; the personal-data inventory table.

---

## 9:35 – 9:55 · Close

**OPEN:** back to the Actions list — a wall of green across the five workflows.

**SAY:** "Every gate you've seen is enforced by a file in this repository, every
accepted risk has a written justification beside it, and both the container and DAST
findings went through a real fix-and-rescan loop. Thanks for watching."

**SHOW (evidence):** the green Actions list across all five workflows.

---

## Time budget

| Segment | Length | Rubric |
|---|---|---|
| Opening | 0:35 | — |
| Pipelines & tools | 0:50 | a.i |
| Unit + integration | 1:10 | a.ii, a.iii |
| Load & stress | 0:35 | a.iv |
| SAST | 0:35 | a.v |
| DAST tool + artifacts | 0:35 | a.vi |
| Containers (live) | 0:55 | b.i, b.iii, b.iv |
| Trivy fix/rescan | 1:25 | b.ii |
| DAST resolution/rescan | 1:15 | c.ii |
| IaC + audit trails | 1:05 | d.i, d.ii |
| Regulatory framework | 0:35 | e |
| Close | 0:20 | — |
| **Total** | **9:55** | |

## If over time — cut in this order (none removes a rubric item)

1. `terraform plan` live demo → just show the files (−20 s)
2. Personal-data inventory table (−15 s)
3. Trivy round 1 compressed to one sentence (−20 s)
4. Opening architecture description → one sentence (−15 s)

## Never cut (the evidence-rich, un-fakeable moments)

- The live terminal (`logs -f` + curl) — b.iii/b.iv
- Trivy round 3 (the gate-bug fix) — b.ii
- The DAST before-vs-after report comparison — c.ii
