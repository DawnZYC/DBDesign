# Terraform + provider version pins.
#
# The Docker provider (kreuzwerker/docker) talks to the local Docker daemon, so
# `terraform apply` provisions the same three-service Strata stack that
# docker-compose.deploy.yml describes — but as declarative, state-tracked
# infrastructure-as-code rather than an imperative `docker compose up`.

terraform {
  required_version = ">= 1.5"

  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
  }
}

provider "docker" {
  # Empty var → null, so the provider falls back to DOCKER_HOST / the default
  # local socket. Set `docker_host` to target a remote daemon (deploy server).
  host = var.docker_host != "" ? var.docker_host : null
}
