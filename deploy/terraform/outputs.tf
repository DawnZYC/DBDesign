output "frontend_url" {
  description = "SPA entry point once the stack is up."
  value       = "http://localhost:${var.frontend_port}"
}

output "backend_health_url" {
  description = "Backend health endpoint used by the deploy smoke test."
  value       = "http://localhost:${var.backend_port}/api/health"
}

output "container_names" {
  value = {
    db       = docker_container.db.name
    backend  = docker_container.backend.name
    frontend = docker_container.frontend.name
  }
}
