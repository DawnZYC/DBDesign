# Compliance as Code — Regulatory Mapping

Strata processes **energy-model technical data** (EcoTEA WP1) — no health
records and no consumer personal data. The applicable frameworks are
therefore chosen for relevance rather than reflex:

* **PDPA (Singapore)** — governing law for any personal data the system does
  touch (user accounts / operator identities, if introduced).
* **GDPR** — reference framework; obligations mirror PDPA closely and cover
  any future EU collaboration.
* **SOC 2 Trust Services Criteria** — used as the *control vocabulary* for
  the engineering process itself (security, availability, change management).
* HIPAA is **not applicable** (no PHI) and intentionally out of scope.

The core claim of "compliance as code": every control below is enforced by a
versioned artifact in this repository — not by policy documents — so the Git
history *is* the audit trail.

## 1. Control mapping

| # | Control (SOC 2 CC / PDPA-GDPR principle) | Implemented by (artifact) | Enforcement |
|---|---|---|---|
| 1 | Change management (CC8.1) | All infra + pipeline defined as code — `.github/workflows/*.yml`, `docker-compose*.yml`, `deploy/` shell, and **`deploy/terraform/`** (Terraform: Docker-provider runtime stack + GitHub-provider policy-as-code); every change is a reviewed commit | Git history, PR review, `terraform plan` drift |
| 2 | Code integrity before release (CC7.1) | `ci.yml`: lint, typecheck, 600+ unit/integration tests, SonarCloud quality gate | Blocking CI |
| 3 | Vulnerability management (CC7.1) | Bandit, pip-audit + triaged ignore list (`security/pip-audit-ignores.txt`), npm audit, Trivy, ZAP — see `VULNERABILITY_ASSESSMENT.md` | Blocking CI (DAST informational v1) |
| 4 | Least-privilege pipeline (CC6.3) | Per-workflow `permissions:` blocks (read-only by default; `packages: write` only where images are pushed) | GitHub Actions |
| 5 | Segregation of environments (CC6.1) | Staging vs production compose project isolation; production deploys gated behind GitHub Environment required reviewers, codified in `deploy/terraform/github-policy/` | `deploy.yml`, Terraform policy-as-code |
| 6 | Immutable release artifacts (CC8.1) | Images tagged by content (`sha-<digest>`) and semver; deploys reference immutable tags; `deploy.sh` auto-rollback | `build-images.yml`, `deploy/` |
| 7 | Secrets management (CC6.1; PDPA Protection / GDPR integrity-confidentiality) | No secrets in the repo (`.env` gitignored); credentials only via GitHub Secrets / env injection | `.gitignore`, workflow design |
| 8 | Data minimisation (PDPA Purpose Limitation / GDPR Art. 5(1)(c)) | Only EcoTEA model data is ingested; the confidential source workbook is excluded from version control and tests synthesise structures instead | `.gitignore`, `tests/test_schema_mapper.py` |
| 9 | Transfer & access boundaries (PDPA / GDPR Art. 32) | CORS restricted to configured origins (no wildcard-with-credentials); DB reachable only inside the compose network, not published | `app/main.py`, compose files |
| 10 | Availability & recoverability (A1.2) | Health checks at every layer (PG healthcheck, `/api/health`, deploy smoke tests); rollback on failed health check | compose files, `deploy.sh` |
| 11 | Monitoring of processing integrity (PI1.4) | Structured logging with configured level; CI artifacts (coverage, JUnit, scan reports) retained per run | `ci.yml`, `LOG_LEVEL` |
| 12 | Audit trail (CC4.1; GDPR accountability Art. 5(2)) | Full Git history incl. pre-commit hooks; CI runs recorded with artifacts; GitHub Security tab retains SARIF scan history | Git + GitHub Actions |

## 2. Personal data inventory (PDPA/GDPR)

| Data | Present today? | Notes |
|---|---|---|
| Energy-model technical data | Yes | Not personal data; confidential source workbook kept out of the repo |
| User accounts / auth identities | No | If added: consent, access, and retention duties activate → revisit rows 7–9 |
| LLM prompts/responses | Transient | Sent to the configured LLM provider; no chat persistence layer in scope. Provider DPAs apply if personal data ever enters prompts |
| Server/access logs | Runtime only | No PII beyond standard request metadata; not shipped off-host |

## 3. Gaps & planned work

* DAST gate is informational until the first triage pass (tracked in
  `VULNERABILITY_ASSESSMENT.md` §5).
* No authentication layer yet — access control is deployment-level
  (network isolation). Required before any multi-user production use.
* langchain/langgraph 1.x migration empties the pip-audit accepted-risk list.
* If user accounts are introduced, add a formal PDPA consent + retention
  policy and a DPIA-style review.
