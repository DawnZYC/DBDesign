# DevSecOps Video — Show Path & Prep Runbook

For `TeamXX- Technical Assessment - DevSecOps.mp4` (10 min). This is the operational
companion to `DEMO_VIDEO_PLAN.md` Part A: it lists **exactly what to open on screen**
for each rubric item, and **what you must prepare or verify before recording**.

Rubric coverage map: a.i–a.vi (CI/CD), b.i–b.iv (containers), c.i–c.ii (vuln
resolution), d.i–d.ii (compliance as code), e (regulatory framework).

---

# PART 1 — What you need to do BEFORE recording

Do these in order. Nothing here is on-camera; it's so the recording has real
artifacts to point at.

## 1.1 Make the green runs exist (critical)

Every "open this run" step below assumes a **successful, recent** run exists. Trigger
them now so they're finished and green by record time.

- [ ] **CI** — push any tiny commit to a branch and open a PR, or re-run the latest CI
      on `main`. Confirm all six jobs are green: `Backend (lint + test)`,
      `Frontend (lint + test + build)`, `DB schema check`, `SonarCloud quality gate`,
      `SAST (Bandit)`, `Dependency audit`.
- [ ] **Build & Publish Images** — confirm the latest run on `main` is green (the one
      you just fixed). You need **both** this green run *and* an earlier **failed** run
      still visible in the Actions history for the Trivy story (c.i). Do not delete the
      failed run.
- [ ] **Load & Stress Test** — this runs on its own triggers. Open `load-test.yml` and
      check when it last ran; if there's no recent green run, trigger it manually
      (Actions → Load & Stress Test → Run workflow) and wait for `locust-reports`.
- [ ] **DAST** — **most likely missing.** `dast.yml` only triggers weekly or on `.zap/**`
      changes, so there may be no artifact to show. Go to Actions → DAST (OWASP ZAP) →
      Run workflow, and wait until `zap-baseline-frontend` / `zap-api-backend` artifacts
      appear. Without this, the a.vi segment has nothing to open.

## 1.2 Pre-download artifacts (so you never wait on a spinner on camera)

From the finished runs, download and unzip these to a local `~/demo-artifacts/` folder:

- [ ] `backend-test-results` → `junit-unit.xml`, `junit-integration.xml`
- [ ] `backend-coverage` → `coverage.xml` (or open the SonarCloud dashboard instead — nicer visual)
- [ ] `locust-reports` → the Locust **HTML** report (this is the one to show; it has charts)
- [ ] `bandit-reports` → `bandit-report.txt`
- [ ] `zap-baseline-frontend` → the ZAP **HTML** report

> Tip: JUnit XML is ugly on screen. If you want testing to look good, open the
> SonarCloud dashboard (coverage %, test count) rather than raw XML, and just *flash*
> the XML for one second as proof the artifact is real.

## 1.3 Get the local stack healthy (for the live container segment)

```bash
cd <repo>
docker compose up -d
docker compose ps          # wait until backend + db + frontend show "healthy"
```

- [ ] All three services healthy.
- [ ] Note the **real container name** — run `docker compose ps` and copy the backend
      container's name (likely `dbdesign-backend-1`; there is no `container_name:` set,
      so it's derived from the folder). You'll need it for the `docker inspect` line.
- [ ] Seed data if you want a live request to return something real:
      `docker compose exec backend python scripts/seed_commodities.py && docker compose exec backend python scripts/seed_rag.py`

## 1.4 Screen hygiene

- [ ] Terminal ≥ 16 pt, high contrast, ~120 columns wide.
- [ ] Browser zoom 110–125 %.
- [ ] Log out of nothing, but **close** any tab showing repo Settings → Secrets, and
      don't run `git remote -v` or anything exposing a token on camera.
- [ ] Do Not Disturb on; close mail/Slack.

## 1.5 Pre-open browser tabs (left to right, in show order)

1. Repo root (file tree)
2. `.github/workflows/` directory
3. Actions → **CI** latest green run
4. Actions → **Load & Stress Test** latest green run
5. Actions → **DAST** latest run
6. Actions → **Build & Publish Images** green run
7. Actions → **Build & Publish Images** the **failed** run (for the Trivy story)
8. GHCR packages page (`github.com/users/DawnZYC/packages` or the repo Packages tab)
9. Security tab → Code scanning (Trivy results)
10. SonarCloud project dashboard
11. A second terminal window/pane for the live request

Also open in your editor, ready to switch to:
`security/VULNERABILITY_ASSESSMENT.md`, `security/.trivyignore`,
`security/COMPLIANCE.md`, `backend/Dockerfile`, and any one `permissions:` block.

---

# PART 2 — On-screen show path, per rubric item

Timings match `DEMO_VIDEO_PLAN.md` Part A. For each item: **OPEN** = what to have on
screen, **DO** = clicks/commands, **SAY** = the one line that names the rubric item.

## a.i — Pipelines and tools used · (0:35–1:30)

- **OPEN:** tab 2 (`.github/workflows/` listing), then `CI_CD_SETUP.md` §1.
- **DO:** point at the five `.yml` files. Then open one workflow and scroll to its
  `permissions:` block.
- **SAY:** "Five pipelines — CI, image build, DAST, load test, deploy — each triggered
  differently and each with least-privilege permissions."

## a.ii / a.iii — Unit & integration testing (result artifacts) · (1:30–2:45)

- **OPEN:** tab 3 (CI run) → expand **`Backend (lint + test)`**.
- **DO:** scroll the step list so the `Unit tests` and `Integration tests (API + e2e)`
  steps are visible. Then scroll to the **Artifacts** panel at the bottom of the run.
  Point at `backend-test-results`, `backend-coverage`, `frontend-test-results`,
  `frontend-coverage`, `frontend-dist`. Cut to your pre-downloaded coverage/JUnit for 2 s.
- **SAY:** "Unit and integration tests run as separate steps, both emitting JUnit XML
  uploaded as result artifacts — here."
- **Note:** integration tests are the `test_routers_*` + `test_excel_importer_e2e`
  suites; mention they hit the real API layer, not mocks.

## a.iv — Load and stress testing (result artifacts) · (2:45–3:25)

- **OPEN:** `load-test.yml` (show the two phase steps), then the Locust **HTML** report.
- **DO:** point at `Phase 1: load test (20 users, 2 min)` and
  `Phase 2: stress test (100 users, 90 s)`, then the `Enforce performance thresholds`
  step. Switch to the Locust HTML report; let the charts sit.
- **SAY:** "Two phases — steady-state load and over-capacity stress — with a threshold
  gate, and the Locust report as the artifact."

## a.v — SAST (tool and result artifacts) · (3:25–3:50)

- **OPEN:** tab 3 → `SAST (Bandit)` job → then SonarCloud dashboard (tab 10).
- **DO:** show the `Bandit scan` step output, point at `bandit-reports` artifact. Flip
  to SonarCloud for the quality-gate visual.
- **SAY:** "SAST is Bandit on the backend, blocking, with the report as an artifact —
  plus SonarCloud as the quality gate."

## a.vi — DAST (tool and result artifacts) · (3:50–4:15)

- **OPEN:** `dast.yml`, then `.zap/rules.tsv`, then the ZAP HTML report.
- **DO:** point at the two scan steps (baseline + API scan). Show `.zap/rules.tsv` (the
  triage log). Open the ZAP HTML report.
- **SAY:** "DAST is OWASP ZAP against the running stack — a baseline scan and an
  OpenAPI-driven API scan — reports uploaded as artifacts."

## b.i — Building and saving images · (5:00–5:25)

- **OPEN:** `backend/Dockerfile` (briefly), then GHCR packages page (tab 8).
- **DO:** point at the multi-stage build (builder → runtime), non-root `USER app`,
  `HEALTHCHECK`. On GHCR, point at the tag list: `sha-<short>`, branch, semver, `latest`.
- **SAY:** "Multi-stage build, published to GHCR, tagged by commit SHA and semver;
  deploys reference the immutable digest."

## b.iii / b.iv — Interact and inspect containers · Container logs · (5:25–6:30) — LIVE

- **OPEN:** your local terminal.
- **DO:** run these, pausing on each output:

```bash
docker compose ps
docker inspect --format '{{.State.Health.Status}}' dbdesign-backend-1   # use YOUR real name
docker compose exec backend python -c "from app.main import app; print(len(app.routes), 'routes')"
docker compose logs -f backend --tail 20
```

  While `logs -f` streams, in the **second pane** hit an endpoint:

```bash
curl -s localhost:8000/api/health
```

  Let the request show up in the streaming log. That's b.iii (interact/inspect) and
  b.iv (logs) demonstrated in one motion.
- **SAY:** "I can exec into the running container, inspect its health, and tail its
  logs live — here's a request landing in the log stream in real time."

## b.ii — Image security (Trivy) · fused with c.i below · (6:30–8:00)

## c.i — Resolution and rescan results of SAST → *shown as the Trivy fix loop* · (6:30–8:00) — CENTREPIECE

> Note: Bandit (the SAST tool) reports zero findings, so there's no SAST fix loop to
> show. Be honest about that and pivot to the **container-image** fix→rescan loop,
> which is a real, three-round resolution story. It's the strongest evidence you have
> for "resolution and rescan," even though the tool is Trivy rather than Bandit.

- **OPEN, in this sequence:**
  1. `build-images.yml` Trivy steps (the two `aquasecurity/trivy-action` steps)
  2. tab 7 — the **failed** run log (show the findings table)
  3. `security/.trivyignore`
  4. `security/VULNERABILITY_ASSESSMENT.md` (§4, the three gated runs)
  5. tab 6 — the **green** run
  6. tab 9 — Security tab SARIF history
- **DO / SAY:** tell the three rounds (see `DEMO_VIDEO_PLAN.md` for the full script):
  round 1 = 13 HIGH triaged three ways; round 2 = two missed transformers CVEs fixed
  by upgrading 4.46.3 → 4.48.0; round 3 = the `unset TRIVY_SEVERITY` gate bug fixed
  with `limit-severities-for-sarif`. End on the green run + SARIF history.
- **SAY the closer:** "Every round — what the scanner said, what changed, what the
  rescan showed — is written up in `VULNERABILITY_ASSESSMENT.md`."

## c.ii — Resolution and rescan results of DAST · (covered in the gaps segment, 9:00–9:50)

> **You have a real gap here.** DAST is still informational (`fail_action: false`) and
> the §5 before/after table is unfilled. Don't fake it. Handle it in the gaps segment:
> "The DAST resolution loop isn't closed yet — the gate is informational, the triage
> procedure is written in §5, and flipping it to blocking is a one-line change once the
> first ZAP baseline is triaged." Owning this reads far better than pretending.
> **If you want to actually close it before recording**, that's a separate task — say
> the word and I'll help fill §5 from a real ZAP run and flip the flag.

## d.i — Infrastructure-as-Code (tools and artifacts) · (8:00–8:30)

- **OPEN:** `docker-compose.yml` / `deploy/docker-compose.deploy.yml` / `deploy/deploy.sh`
  / the workflow files.
- **SAY (the honest framing):** "Our infrastructure is declarative and versioned —
  compose files, the deploy script, the workflows. That's configuration-as-code. There's
  no Terraform/Ansible provisioning layer yet, because there's no cloud account to
  provision against — `CI_CD_SETUP.md` §7 shows switching to a real server is a
  three-secret change, not a code change."

## d.ii — Version control audit trails · (8:30–9:00)

- **OPEN:** `security/COMPLIANCE.md` control table, then a terminal `git log --oneline`
  or the GitHub PR list.
- **SAY:** "Every control maps to a versioned artifact, so the Git history *is* the
  audit trail — control 12 in this table."

## e — Specific regulatory framework · (part of 8:00–9:00)

- **OPEN:** `security/COMPLIANCE.md` top section + the framework bullets.
- **SAY:** "We use SOC 2 criteria as the control vocabulary, PDPA as governing law,
  GDPR as reference — and we explicitly rule out HIPAA, because there's no health data.
  Naming the reason matters more than listing frameworks."

## Gaps & close · (9:00–9:50)

- **OPEN:** `COMPLIANCE.md` §3 and `VULNERABILITY_ASSESSMENT.md` §5.
- **SAY:** volunteer the three gaps — DAST gate informational (c.ii), no auth layer, no
  provisioning IaC — then close on "every gate is a file in this repo, every accepted
  risk has a written justification."

---

# PART 3 — Quick prep checklist (tear-off)

**Must exist before recording:**
- [ ] Green CI run (6 jobs)
- [ ] Green Build & Publish run + the old failed run still visible
- [ ] Green Load & Stress run with `locust-reports`
- [ ] **DAST run triggered manually** so ZAP artifacts exist ← easy to forget
- [ ] Local stack healthy; real backend container name noted
- [ ] Artifacts pre-downloaded (Locust HTML, ZAP HTML, bandit txt, coverage)
- [ ] 11 tabs pre-opened in order; editor files ready
- [ ] Screen hygiene: font size, zoom, DND, no secrets tab

**Two moments that must be live (can't be faked with slides):**
- [ ] The `logs -f` + curl request in the container segment (b.iii/b.iv)
- [ ] The three-round Trivy fix→rescan story (b.ii/c.i)

**Two gaps to own out loud, not hide:**
- [ ] No SAST fix loop (Bandit = 0 findings) → pivot to the Trivy loop
- [ ] DAST resolution not closed (c.ii) → explain the one-line flip, offer it as next step
