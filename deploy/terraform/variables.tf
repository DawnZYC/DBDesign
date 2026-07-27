# Inputs for the Strata runtime stack.
#
# Defaults mirror deploy/docker-compose.deploy.yml so `terraform apply` with no
# tfvars reproduces the same staging stack the deploy pipeline brings up.

variable "docker_host" {
  description = "Docker daemon endpoint. Empty string = provider default (local socket)."
  type        = string
  default     = ""
}

variable "environment" {
  description = "Environment name; used as the resource name prefix (staging / prod)."
  type        = string
  default     = "staging"
}

variable "backend_image" {
  description = "Immutable backend image ref (sha- or vX.Y.Z tag), matching build-images.yml output."
  type        = string
  default     = "ghcr.io/dawnzyc/dbdesign-backend:latest"
}

variable "frontend_image" {
  description = "Immutable frontend image ref."
  type        = string
  default     = "ghcr.io/dawnzyc/dbdesign-frontend:latest"
}

variable "postgres_image" {
  type    = string
  default = "postgres:17-alpine"
}

variable "backend_port" {
  description = "Host port mapped to the backend container's 8000."
  type        = number
  default     = 8000
}

variable "frontend_port" {
  description = "Host port mapped to the frontend container's 80."
  type        = number
  default     = 5173
}

variable "postgres_password" {
  description = "Postgres password. Override in production via TF_VAR_postgres_password; never commit a real value."
  type        = string
  default     = "postgres"
  sensitive   = true
}

variable "allowed_origins" {
  type    = string
  default = "http://localhost:5173,http://127.0.0.1:5173"
}

variable "llm_provider" {
  type    = string
  default = "openai"
}

variable "embedding_provider" {
  type    = string
  default = "huggingface"
}

variable "openai_api_key" {
  description = "Optional; injected into the backend env if set."
  type        = string
  default     = ""
  sensitive   = true
}
