# Infrastructure as Code (Terraform)

Two Terraform modules cover the two kinds of infrastructure this project owns:
the **runtime stack** (containers) and the **governance controls** (repository
policy). Both are declarative, version-controlled, and drift-detectable — the
difference from the compose files and `deploy.sh` is that Terraform tracks
**state**, so `plan` tells you what will change before it changes.

## 1. Runtime stack — this directory

Provisions the Strata three-service stack (Postgres + backend + frontend) on a
Docker daemon via the `kreuzwerker/docker` provider. Topology matches
`deploy/docker-compose.deploy.yml` exactly; it pulls the same immutable GHCR
image refs the build pipeline publishes.

```bash
cd deploy/terraform
cp terraform.tfvars.example terraform.tfvars   # edit image tags
export TF_VAR_postgres_password=...            # keep secrets out of the file

terraform init
terraform plan        # preview: network + 2 volumes + 3 containers
terraform apply
terraform output      # frontend_url, backend_health_url, container_names
terraform destroy     # tear down
```

**Scope note (honest):** the Docker provider orders containers with
`depends_on` but does not block on health — the deploy pipeline's smoke test
(`deploy.sh`) remains the readiness gate. This module is the declarative
description of the runtime; the pipeline still owns rollout and health
verification.

## 2. Governance controls — `github-policy/`

Codifies the branch-protection and environment controls that `COMPLIANCE.md`
describes, using the GitHub provider. This turns "we protect `main`" and
"production needs a reviewer" from clicked-in settings into reviewable,
drift-detectable code.

```bash
cd deploy/terraform/github-policy
export GITHUB_TOKEN=ghp_...   # needs repo admin scope
terraform init
terraform plan                # shows the required checks + reviewer rules
```

Fill in real reviewer user/team IDs before `apply`.

## Relationship to the rest of the repo

| Layer | Artifact | Tool |
|---|---|---|
| Local dev stack | `docker-compose.yml` | Docker Compose |
| Deploy stack (imperative) | `deploy/docker-compose.deploy.yml` + `deploy.sh` | Compose + shell |
| **Deploy stack (declarative, stateful)** | **`deploy/terraform/`** | **Terraform + Docker provider** |
| **Repo governance (policy-as-code)** | **`deploy/terraform/github-policy/`** | **Terraform + GitHub provider** |
| Pipeline definitions | `.github/workflows/*.yml` | GitHub Actions |

All are infrastructure-as-code; Terraform adds state tracking and a `plan`
step on top of the compose-based flow.
