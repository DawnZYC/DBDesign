# Policy-as-code — the governance controls, as Terraform.
#
# COMPLIANCE.md claims branch protection on `main` and a production environment
# gated behind required reviewers. This module makes those controls *code*: the
# repository settings are provisioned and drift-detectable, not clicked into the
# GitHub UI once and forgotten. This is the compliance-as-code half of IaC.
#
# Apply requires a token with repo admin scope:
#   export GITHUB_TOKEN=ghp_...
#   terraform init && terraform apply
#
# Kept as a separate module from the runtime stack because it targets a
# different provider (GitHub API, not the Docker daemon) and a different
# blast radius (repo settings vs. containers).

terraform {
  required_version = ">= 1.5"
  required_providers {
    github = {
      source  = "integrations/github"
      version = "~> 6.0"
    }
  }
}

variable "owner" {
  type    = string
  default = "DawnZYC"
}

variable "repository" {
  type    = string
  default = "DBDesign"
}

provider "github" {
  owner = var.owner
  # token from GITHUB_TOKEN env var
}

# --- Branch protection on main: CI + image build must pass before merge,
#     and a review is required. Mirrors COMPLIANCE.md control #1 and #2.
resource "github_branch_protection" "main" {
  repository_id = var.repository
  pattern       = "main"

  required_status_checks {
    strict = true
    contexts = [
      "Backend (lint + test)",
      "Frontend (lint + test + build)",
      "DB schema check",
      "SonarCloud quality gate",
      "SAST (Bandit)",
      "Dependency audit",
      "Build backend",
      "Build frontend",
    ]
  }

  required_pull_request_reviews {
    required_approving_review_count = 1
    dismiss_stale_reviews           = true
  }

  enforce_admins = false
}

# --- Production environment gated behind required reviewers.
#     Mirrors COMPLIANCE.md control #5 (segregation of environments).
resource "github_repository_environment" "production" {
  repository  = var.repository
  environment = "production"

  reviewers {
    # Replace with real GitHub user IDs (numeric) or team IDs before apply.
    # users = [<your-user-id>]
  }

  deployment_branch_policy {
    protected_branches     = true
    custom_branch_policies = false
  }
}

resource "github_repository_environment" "staging" {
  repository  = var.repository
  environment = "staging"
}
