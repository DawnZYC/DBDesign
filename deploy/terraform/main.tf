# Strata runtime stack as infrastructure-as-code.
#
# Declares the same topology as deploy/docker-compose.deploy.yml — an isolated
# network, two persistent volumes, and three containers (db, backend, frontend)
# — so the deployed environment is version-controlled and reproducible from
# state, not from remembered CLI commands.

locals {
  prefix = "strata-${var.environment}"
}

# --- Network: private bridge; only published ports are reachable from the host.
resource "docker_network" "strata" {
  name = "${local.prefix}-net"
}

# --- Persistent volumes (Postgres data + ChromaDB vector store).
resource "docker_volume" "pg_data" {
  name = "${local.prefix}-pg-data"
}

resource "docker_volume" "chroma_data" {
  name = "${local.prefix}-chroma-data"
}

# --- Images: pull the exact refs the build pipeline published.
resource "docker_image" "postgres" {
  name = var.postgres_image
}

resource "docker_image" "backend" {
  name = var.backend_image
}

resource "docker_image" "frontend" {
  name = var.frontend_image
}

# --- Database: schema DDL in /sql runs on first start, in filename order.
resource "docker_container" "db" {
  name  = "${local.prefix}-db"
  image = docker_image.postgres.image_id

  env = [
    "POSTGRES_USER=postgres",
    "POSTGRES_PASSWORD=${var.postgres_password}",
    "POSTGRES_DB=ecotea",
  ]

  networks_advanced {
    name = docker_network.strata.name
  }

  volumes {
    volume_name    = docker_volume.pg_data.name
    container_path = "/var/lib/postgresql/data"
  }

  # Bind-mount the repo's SQL so first-boot init matches every other environment.
  volumes {
    host_path      = abspath("${path.module}/../../sql")
    container_path = "/docker-entrypoint-initdb.d"
    read_only      = true
  }

  healthcheck {
    test     = ["CMD-SHELL", "pg_isready -U postgres -d ecotea"]
    interval = "5s"
    timeout  = "3s"
    retries  = 10
  }

  restart = "unless-stopped"
}

# --- Backend: FastAPI app; HEALTHCHECK is baked into the image.
resource "docker_container" "backend" {
  name  = "${local.prefix}-backend"
  image = docker_image.backend.image_id

  env = [
    "DATABASE_URL=postgresql+psycopg://postgres:${var.postgres_password}@${docker_container.db.name}:5432/ecotea",
    "ALLOWED_ORIGINS=${var.allowed_origins}",
    "LOG_LEVEL=INFO",
    "LLM_PROVIDER=${var.llm_provider}",
    "EMBEDDING_PROVIDER=${var.embedding_provider}",
    "OPENAI_API_KEY=${var.openai_api_key}",
    "CHROMA_PERSIST_DIR=/app/chroma_data",
  ]

  ports {
    internal = 8000
    external = var.backend_port
  }

  networks_advanced {
    name = docker_network.strata.name
  }

  volumes {
    volume_name    = docker_volume.chroma_data.name
    container_path = "/app/chroma_data"
  }

  # Ordering only. The Docker provider does not block on health; the deploy
  # pipeline's smoke test is what gates readiness (see deploy.sh).
  depends_on = [docker_container.db]

  restart = "unless-stopped"
}

# --- Frontend: nginx serving the SPA and reverse-proxying /api.
resource "docker_container" "frontend" {
  name  = "${local.prefix}-frontend"
  image = docker_image.frontend.image_id

  ports {
    internal = 80
    external = var.frontend_port
  }

  networks_advanced {
    name = docker_network.strata.name
  }

  depends_on = [docker_container.backend]

  restart = "unless-stopped"
}
