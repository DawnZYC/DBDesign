# Video Plan — Two Deliverables

| File | Rubric | Length | Angle |
|---|---|---|---|
| `TeamXX- Technical Assessment - DevSecOps.mp4` | Rubrics III, items a–e | 10 min | **Audit.** Walk the checklist. Prove each artifact exists, and explain the decision behind it. |
| `TeamXX- Presentation Assessment CICD Demo.mp4` | Rubrics IV, item 2 | 5 min | **Motion.** Follow one change from keyboard to production. Show the pipeline *running*, not catalogued. |

Both cover DevSecOps, so the risk is shooting the same video twice. The split
that keeps them distinct:

- **Technical** answers *"did you build it, and do you understand it?"* — it stops,
  opens files, and explains trade-offs. Structure follows the rubric's own ordering
  so a grader can tick along.
- **Presentation** answers *"does it actually work?"* — it never stops moving.
  One narrative thread, no file tours, no justifications. A gate gets one sentence
  ("a fixable HIGH stops the build here"), not a story.

Where both touch the same asset, use different depth. Trivy is the clearest case:
in Presentation it's a one-line gate the commit passes through; in Technical it's a
90-second three-round debugging story.

Language: English narration throughout. Script style: timeline + talking points.

---

## Pre-flight (applies to both)

**Record in segments and splice.** A single take burns 40 minutes in retries.

- [ ] Local stack up and healthy (`docker compose up -d`) before recording
- [ ] Terminal ≥ 16 pt, high contrast, ~120 cols; browser zoom 110–125 %
- [ ] Notifications off, Do Not Disturb on
- [ ] **No secrets on screen**: no `.env`, no Settings → Secrets, no tokens in `git remote -v`
- [ ] Artifacts pre-downloaded (Locust HTML, ZAP HTML, bandit report) — never wait on a download in-frame
- [ ] Trigger `dast.yml` manually once beforehand so a ZAP artifact exists to show

**Tabs to pre-open, in switching order:**

1. Repo root file tree
2. `.github/workflows/` listing
3. Actions → CI run **#64** (green, `main`)
4. Actions → Load & Stress Test (latest green)
5. Actions → DAST (latest)
6. Actions → Build & Publish Images **#16** (green) — plus an earlier **failed** run for the Trivy story
7. GHCR package page with the tag list
8. Security tab → Code scanning → Trivy
9. SonarCloud dashboard
10. Local terminal

---

# Part A — Technical Assessment · DevSecOps (10:00)

Runs to 9:50, leaving 10 s of slack. Framing: follow one commit from PR to
production, naming each rubric artifact as it appears — a working pipeline
rather than a checklist recital, but every item still spoken aloud.

### 0:00 – 0:35 · Opening

**Screen:** README top / architecture section.

**Say:**
- Product in one sentence: Strata — multi-agent energy-model analytics. FastAPI + React + Postgres, LangGraph agent layer.
- Scope in one sentence: "I'll follow a single commit from pull request to deployed container, pointing out each DevSecOps artifact as it appears."
- Signpost four blocks: pipeline & testing → containers → vulnerability management → compliance.

---

### 0:35 – 1:30 · Pipelines and tools (55 s) — **a.i**

**Screen:** `.github/workflows/` listing, then `CI_CD_SETUP.md` §1.

**Say:**
- Five workflows, one job focus each: `ci.yml` (lint/test/quality/SAST/SCA), `build-images.yml` (build + Trivy + publish), `dast.yml` (ZAP), `load-test.yml` (Locust), `deploy.yml` (staging/production).
- Trigger model: CI on every PR and push; images on `main` and tags; DAST weekly plus on demand; deploy behind a GitHub Environment with required reviewers.
- Branch protection on `main` makes CI + build the merge gate.
- Point at a `permissions:` block — read-only by default, `packages: write` only where images are pushed. Least privilege lives in the pipeline definition, not a policy doc.

---

### 1:30 – 2:45 · Unit and integration testing (75 s) — **a.ii, a.iii**

**Screen:** CI #64 → backend job expanded → scroll to Artifacts panel.

**Say / do:**
- Step order: ruff lint → ruff format → apply SQL schema → unit tests → integration tests (API + end-to-end).
- Integration tests run against a real Postgres service container, not mocks.
- Scroll the **Artifacts** panel: `backend-test-results`, `backend-coverage`, `frontend-test-results`, `frontend-coverage`, `frontend-dist`.
- Open a pre-downloaded JUnit XML or coverage HTML for two seconds — proof the artifact is real, not just a name.
- Mention the `db-schema` job: SQL applied in order, expected tables verified, drift fails CI.

> Cuttable if running long: the `db-schema` mention (−10 s).

---

### 2:45 – 3:25 · Load and stress testing (40 s) — **a.iv**

**Screen:** `load-test.yml` two phase steps → Locust HTML report.

**Say / do:**
- Two phases, deliberately distinct: **load** = 20 users / 2 min (steady state), **stress** = 100 users / 90 s (past expected capacity).
- Show "Enforce performance thresholds" — the job fails on p95 latency and failure-rate regression. A gate, not a report.
- Open the Locust HTML from `locust-reports`; let the charts hold while you talk.

---

### 3:25 – 4:15 · SAST and SCA (50 s) — **a.v**

**Screen:** `ci.yml` → `sast-bandit` → `bandit-reports` artifact → SonarCloud dashboard.

**Say:**
- **Bandit** on `backend/app`, blocking. Two invocations by design: one `--exit-zero` to always emit a readable txt report, one that actually gates.
- **SonarCloud** quality gate consumes both coverage reports — smells, duplication, security hotspots.
- **SCA layered on SAST:** `pip-audit` and `npm audit`, both blocking, both driven by triaged ignore lists with written justifications.
- Show `security/pip-audit-ignores.txt` — every entry is an accepted risk with a stated reason, not blanket suppression.

**Written line, weak spot c.i:**
> "Bandit reports zero findings today, so I'll be upfront: the interesting fix-and-rescan evidence isn't here — it's in the dependency and container layers, and I'll show you a real one in ninety seconds."

---

### 4:15 – 5:00 · DAST (45 s) — **a.vi**

**Screen:** `dast.yml` → `.zap/rules.tsv` → ZAP HTML report.

**Say:**
- Two scans against the **running full stack**, brought up with the same compose file used for deployment — the real deployed topology, not a test harness.
- Scan 1: ZAP **baseline** passive scan of the SPA through nginx, which also exercises the `/api` reverse proxy.
- Scan 2: ZAP **API scan** driven by the OpenAPI spec exported from the live backend — endpoint coverage comes from the spec, not guesswork.
- Weekly scheduled rescan; reports land as `zap-baseline-frontend` / `zap-api-backend`.
- Show `.zap/rules.tsv` — the triage log, currently one ignored rule with its justification inline.

---

### 5:00 – 6:30 · Container management, live terminal (90 s) — **b.i, b.iii, b.iv**

**Screen:** `build-images.yml` briefly → GHCR package page → **local terminal**.

**Say (build/publish, ~25 s):**
- Multi-stage Dockerfile: builder installs into an isolated venv; runtime carries only that venv plus app code. Non-root `app` user, tini as PID 1, `HEALTHCHECK` baked in.
- Buildx with GitHub Actions layer cache.
- On GHCR, show the tag set: `sha-<short>`, branch, semver, `latest`. Deploys reference the **immutable digest**, not a floating tag.

**Do (live, ~65 s) — this segment must be live:**

```bash
docker compose ps                    # health status of every service
docker inspect --format '{{.State.Health.Status}}' <backend-container>
docker compose exec backend python -c "from app.main import app; print(len(app.routes), 'routes')"
docker compose logs -f backend --tail 20
```

While `logs -f` streams, hit an endpoint from a second pane or the browser and let
the request appear in the log stream. That single moment demonstrates b.iii and
b.iv more convincingly than any narration.

---

### 6:30 – 8:00 · Image security and a real fix→rescan loop (90 s) — **b.ii, c.i** — *centrepiece*

**Screen:** Trivy steps → the **failed** run log → `.trivyignore` → `VULNERABILITY_ASSESSMENT.md` → the green run → Security tab SARIF.

**Say — three rounds, because that's what actually happened:**

- **Setup:** Trivy runs twice per image. A non-blocking table scan for log readability, and a blocking scan whose exit code gates the build. Unfixable base-image CVEs are excluded — you can't act on them.
- **Round 1:** turning the gate on failed the build immediately — 13 HIGH on the backend. Triaged three ways: *fixed* (setuptools/wheel vendoring vulnerable jaraco.context, upgraded in both Docker stages), *accepted* (starlette / langchain CVEs whose only fix is a breaking 1.x major, mirrored from the pip-audit triage), *accepted with usage justification* (transformers CVEs requiring attacker-supplied models or `trust_remote_code`, neither of which this system does).
- **Round 2:** still red. Two transformers CVEs from the same advisory batch — 2024-11392 and 11393 — had been missed when their sibling 11394 was triaged. Resolution was a **fix, not an ignore**: transformers 4.46.3 → 4.48.0, inside the 4.x line, keeping the pinned sentence-transformers working. The redundant ignore entry was then deleted.
- **Round 3:** still red — with zero HIGH findings left. The cause was the gate itself. `trivy-action`'s entrypoint runs `unset TRIVY_SEVERITY` whenever format is SARIF and `limit-severities-for-sarif` isn't set — it even logs "Building SARIF report with all severities". The blocking step was scanning at *every* severity and failing on fixable LOW/MEDIUM findings the table step never displayed. Fixed by setting that flag.
- **Now green.** Show the passing run, then SARIF history in the Security tab.

**Land it:**
> "This is the part I most wanted to show, because it's the difference between having a gate and operating one. Every round is written up in `VULNERABILITY_ASSESSMENT.md` — what the scanner said, what changed, what the rescan showed, and what was accepted and why."

---

### 8:00 – 9:00 · Compliance as code (60 s) — **d.ii, e**

**Screen:** `security/COMPLIANCE.md` control table → `git log --oneline` / PR list → a `permissions:` block.

**Say:**
- Twelve controls, each mapped to a **versioned artifact** rather than a policy document: change management → workflow definitions; code integrity → blocking CI; vulnerability management → the scanner set; least privilege → `permissions:`; immutable releases → digest-pinned deploys with auto-rollback.
- **Framework choice, stated deliberately:** SOC 2 Trust Services Criteria as the control vocabulary for the engineering process; PDPA as governing law; GDPR as reference framework. **HIPAA explicitly out of scope** — energy-model technical data, no PHI. Say the *reason* aloud; naming a framework you don't need is worse than excluding it with an argument.
- Personal-data inventory: what's held today, what obligations activate if auth is added.
- **Audit trail:** git history plus enforced PR review, CI runs with retained artifacts, SARIF history in the Security tab. The repository *is* the evidence.

**Written line, weak spot d.i:**
> "On infrastructure-as-code I'll be precise rather than generous with myself. Everything here is declarative and versioned — compose files, the deploy script, the workflow definitions — and that's configuration as code. What there isn't is a provisioning layer: no Terraform, no Ansible. That's because there's no cloud account to provision against yet. Section 7 of the setup guide shows the switch to a real server is a three-secret configuration change, not a code change. If provisioning is in scope, that's the obvious next module."

---

### 9:00 – 9:50 · Known gaps and close (50 s) — **c.ii**

**Screen:** `COMPLIANCE.md` §3 and `VULNERABILITY_ASSESSMENT.md` §5.

**Say — volunteer the gaps before you're asked; it reads as control, not weakness:**

1. **DAST gate is informational.** `fail_action` is still `false` and the §5 before/after table is unfilled — the first triage pass isn't complete. The procedure is written; the flip is one line once the baseline is clean.
2. **No authentication layer.** Access control today is deployment-level network isolation. Required before multi-user production use, and it activates rows 7–9 of the personal-data inventory.
3. **No provisioning IaC**, per the previous segment.

**Close:**
> "Every gate you've seen is enforced by a file in this repository, and every accepted risk has a written justification next to it."

---

### Part A time budget

| Segment | Length | Rubric |
|---|---|---|
| Opening | 0:35 | — |
| Pipelines & tools | 0:55 | a.i |
| Unit + integration | 1:15 | a.ii, a.iii |
| Load & stress | 0:40 | a.iv |
| SAST + SCA | 0:50 | a.v |
| DAST | 0:45 | a.vi |
| Containers (live) | 1:30 | b.i, b.iii, b.iv |
| Trivy + fix/rescan | 1:30 | b.ii, c.i |
| Compliance as code | 1:00 | d.i, d.ii, e |
| Gaps & close | 0:50 | c.ii |
| **Total** | **9:50** | |

**If over time, cut in this order:** `db-schema` mention (−10 s) → personal-data
inventory table (−15 s) → Trivy round 1 compressed to one sentence (−20 s) →
opening product description down to one sentence (−15 s).

**Never cut:** the live terminal segment, or round 3 of the Trivy story. Those are
the only two moments that can't be faked with a slide deck.

---

# Part B — Presentation Assessment · CICD Demo (5:00)

Runs to 4:55. **One continuous story: a single change travelling from a text
editor to a running production container.** No file tours, no justifications, no
gap disclosure — those belong to Part A. If a segment here makes the viewer stop
and read, it's the wrong segment.

Ideal prep: make a small, genuinely demonstrable change beforehand (a copy tweak
or an added assertion), push it to a branch, and let CI finish — so you're
narrating a *real* run, not a replay. Keep the PR unmerged until you record.

### 0:00 – 0:25 · The change (25 s)

**Screen:** editor with the one-line diff, then terminal.

**Say:**
- "Strata is a multi-agent analytics platform. I'm going to make one small change and follow it all the way to production."
- Show the edit. `git commit` — let the **pre-commit hooks** run on camera (ruff/prettier). First gate, before code ever leaves the laptop.
- `git push`.

---

### 0:25 – 1:35 · CI on the pull request (70 s)

**Screen:** GitHub PR page, checks section populating → click into the CI run.

**Say — narrate as the checks resolve, keep moving:**
- Opening the PR fires CI: backend lint and tests, frontend lint/typecheck/tests, DB schema verification, SonarCloud quality gate, Bandit for SAST, pip-audit and npm audit for dependencies.
- Point at the jobs turning green in sequence. Mention the counts, not the mechanics.
- Show the artifacts appearing on the run — test results, coverage, scan reports.
- Land on branch protection: "Until every one of these passes, the merge button stays disabled." Show the greyed-out merge button if you can catch it mid-run.

---

### 1:35 – 2:35 · Merge, build, and the security gate (60 s)

**Screen:** merge the PR → Actions picks up Build & Publish → GHCR page.

**Say:**
- Merge to `main` triggers image builds for backend and frontend in parallel.
- Multi-stage build, layer cache, non-root runtime.
- **Trivy scans the freshly built image before anything is published.** One sentence only: "If a fixable HIGH or CRITICAL is found, the build stops here and no image reaches the registry — that gate has actually caught things, which I go through in the technical video."
- Show GHCR with new tags appearing: `sha-<short>`, `main`, `latest`.
- Flash the Security tab — scan results are recorded per run automatically.

> This is where the two videos diverge most. Resist telling the Trivy story here.

---

### 2:35 – 3:45 · Deploy (70 s)

**Screen:** Actions → Deploy run → then the running application in a browser.

**Say:**
- Deploy resolves an **immutable digest**, never a floating tag — the thing tested is bit-for-bit the thing shipped.
- Staging goes automatically; smoke tests hit health, key API routes, and the nginx `/api` proxy.
- Production sits behind a GitHub Environment with **required reviewers** — show the approval gate.
- Approve it, then switch to the browser and show the change live in the application. Close the loop visually: the edit from 0:00 is now on screen in a deployed container.
- One line on rollback: "If the post-deploy health check fails, `deploy.sh` rolls back to the previous digest automatically."

---

### 3:45 – 4:55 · The pipeline keeps running (70 s)

**Screen:** load-test run with Locust charts → DAST schedule → back to a wide shot of the Actions list.

**Say:**
- "Shipping isn't the end of it — three things keep running against what's deployed."
- **Load and stress:** Locust drives 20 users steady, then 100 users past capacity; the job fails on latency and error-rate thresholds. Show the charts.
- **DAST:** OWASP ZAP scans the running stack weekly — passive scan through nginx plus an OpenAPI-driven API scan.
- **Dependency and image scanning** re-run on every build, so a CVE published tomorrow against a dependency pinned today fails the next build. (Keep this to one sentence.)
- **Close on the Actions list** — a wall of green runs across five workflows: "Every one of these is defined in the repository, and every gate you've seen either passed or stopped the change."

### Part B time budget

| Segment | Length |
|---|---|
| The change | 0:25 |
| CI on the PR | 1:10 |
| Merge, build, security gate | 1:00 |
| Deploy | 1:10 |
| Pipeline keeps running | 1:10 |
| **Total** | **4:55** |

**If over time:** compress the load-test detail to one sentence (−20 s), or drop the
rollback line (−10 s). **Never cut** the browser moment at 3:45 — seeing the edit
live in a deployed container is the whole point of this video.
