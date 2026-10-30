resource "google_storage_bucket" "artifacts" {
  for_each = toset(["data", "models", "results", "release"])

  name                        = "${var.bucket_prefix}-${each.value}"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  # This removes only unfinished multipart uploads, never completed objects.
  lifecycle_rule {
    action {
      type = "AbortIncompleteMultipartUpload"
    }
    condition {
      age = 7
    }
  }

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [google_project_service.required["storage.googleapis.com"]]
}
