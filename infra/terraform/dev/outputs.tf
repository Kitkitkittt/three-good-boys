output "project_id" {
  value = var.project_id
}

output "region" {
  value = var.region
}

output "service_urls" {
  description = "Web is IAP-protected; API and dispatcher require their distinct service identities."
  value = {
    web        = google_cloud_run_v2_service.web.uri
    api        = google_cloud_run_v2_service.api.uri
    dispatcher = local.dispatcher_url
  }
}

output "service_audiences" {
  description = "Path-free Google service ID-token audiences, not human IAP assertion audiences."
  value = {
    api        = google_cloud_run_v2_service.api.uri
    dispatcher = local.dispatcher_url
  }
}

output "iap_audience" {
  description = "Signed human assertion audience verified by the private API."
  value       = local.iap_audience
}

output "dispatch_queue" {
  value = {
    name     = google_cloud_tasks_queue.dispatch.name
    location = google_cloud_tasks_queue.dispatch.location
  }
}

output "reconcile_scheduler" {
  value = google_cloud_scheduler_job.reconcile.id
}

output "runtime_service_accounts" {
  value = { for name, account in google_service_account.runtime : name => account.email }
}

output "artifact_buckets" {
  value = { for name, bucket in google_storage_bucket.artifacts : name => bucket.name }
}

output "image_repository" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "github_wif_provider" {
  value = google_iam_workload_identity_pool_provider.github.name
}

output "ci_deploy_service_account" {
  value = google_service_account.ci["deploy"].email
}

output "ci_build_service_account" {
  description = "Registry writer only; no GitHub impersonation, source access or build-submission privilege is implied."
  value       = google_service_account.ci["build"].email
}

output "budget_name" {
  value = google_billing_budget.development.name
}
