resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = "lifemate-images"
  description   = "Private LifeMate Docker images"
  format        = "DOCKER"

  docker_config {
    immutable_tags = true
  }

  cleanup_policy_dry_run = false
  cleanup_policies {
    id     = "delete-old-untagged"
    action = "DELETE"
    condition {
      tag_state  = "UNTAGGED"
      older_than = "2592000s"
    }
  }

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [google_project_service.required["artifactregistry.googleapis.com"]]
}
