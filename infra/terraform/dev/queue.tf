resource "google_cloud_tasks_queue" "dispatch" {
  name     = "lifemate-dispatch"
  location = var.region

  rate_limits {
    max_concurrent_dispatches = 1
    max_dispatches_per_second = 1
  }

  retry_config {
    max_attempts       = 5
    max_retry_duration = "300s"
    min_backoff        = "10s"
    max_backoff        = "300s"
    max_doublings      = 3
  }

  depends_on = [google_project_service.required["cloudtasks.googleapis.com"]]
}
