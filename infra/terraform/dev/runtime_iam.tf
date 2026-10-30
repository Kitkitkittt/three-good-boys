# Firestore has project IAM rather than a database IAM resource in this provider.
# Restrict the data-plane role to the existing application database. Server-side
# credentials bypass Firestore rules: application role checks remain mandatory.
resource "google_project_iam_member" "firestore" {
  for_each = toset(["api", "dispatcher"])
  project  = var.project_id
  role     = "roles/datastore.user"
  member   = "serviceAccount:${google_service_account.runtime[each.key].email}"
  condition {
    title      = "lifemate_application_database"
    expression = "resource.name == ${jsonencode("projects/${var.project_id}/databases/${google_firestore_database.default.name}")}"
  }
}

resource "google_cloud_tasks_queue_iam_member" "enqueue" {
  for_each = toset(["api", "dispatcher"])
  project  = var.project_id
  location = google_cloud_tasks_queue.dispatch.location
  name     = google_cloud_tasks_queue.dispatch.name
  role     = "roles/cloudtasks.enqueuer"
  member   = "serviceAccount:${google_service_account.runtime[each.key].email}"
}

resource "google_service_account_iam_member" "task_act_as" {
  for_each           = toset(["api", "dispatcher"])
  service_account_id = google_service_account.runtime["task_caller"].name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.runtime[each.key].email}"
}

resource "google_service_account_iam_member" "worker_act_as" {
  service_account_id = google_service_account.runtime["worker"].name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.runtime["dispatcher"].email}"
}

# Batch creates dynamic jobs and has no per-job IAM policy. These permissions
# omit broad jobEditor, IAM, billing and Compute administration. The documented
# role index has no batch.jobs.cancel permission; jobs.delete is a candidate
# grant for cancel. Authorization must be proven by approved smoke.
resource "google_project_iam_custom_role" "dispatcher_batch" {
  project     = var.project_id
  role_id     = "lifemateBatchDispatcher"
  title       = "LifeMate Batch lifecycle"
  description = "Create and reconcile dynamic Batch jobs; cancel without Compute or IAM administration."
  permissions = [
    "batch.jobs.create",
    "batch.jobs.get",
    "batch.jobs.delete",
    "batch.operations.get",
    "batch.tasks.get",
    "batch.tasks.list",
  ]
}

resource "google_project_iam_member" "dispatcher_batch" {
  project = var.project_id
  role    = google_project_iam_custom_role.dispatcher_batch.name
  member  = "serviceAccount:${google_service_account.runtime["dispatcher"].email}"
}

resource "google_project_iam_custom_role" "result_reader" {
  project     = var.project_id
  role_id     = "lifemateResultReader"
  title       = "LifeMate result object reader"
  description = "Read explicitly named generation-pinned result objects without list, create, overwrite or delete."
  permissions = ["storage.objects.get"]
}

resource "google_storage_bucket_iam_member" "api_results" {
  bucket = google_storage_bucket.artifacts["results"].name
  role   = google_project_iam_custom_role.result_reader.name
  member = "serviceAccount:${google_service_account.runtime["api"].email}"
  condition {
    title = "approved_redacted_metadata"
    expression = join(" || ", [for prefix in sort(tolist(var.api_result_prefixes)) :
      "resource.name.startsWith(${jsonencode("projects/_/buckets/${google_storage_bucket.artifacts["results"].name}/objects/${prefix}")})"
    ])
  }
}

resource "google_storage_bucket_iam_member" "dispatcher_results" {
  bucket = google_storage_bucket.artifacts["results"].name
  role   = google_project_iam_custom_role.result_reader.name
  member = "serviceAccount:${google_service_account.runtime["dispatcher"].email}"
  condition {
    # The dispatcher reads the worker's manifest (manifests/) and re-reads
    # pinned result objects beneath var.result_prefix to verify checksums.
    # Nothing else in the results bucket is readable.
    title = "approved_result_verification"
    expression = join(" || ", [
      "resource.name.startsWith(${jsonencode("projects/_/buckets/${google_storage_bucket.artifacts["results"].name}/objects/manifests/")})",
      "resource.name.startsWith(${jsonencode("projects/_/buckets/${google_storage_bucket.artifacts["results"].name}/objects/${var.result_prefix}")})",
    ])
  }
}

resource "google_storage_bucket_iam_member" "worker_inputs" {
  for_each = toset(["data", "models"])
  bucket   = google_storage_bucket.artifacts[each.key].name
  role     = "roles/storage.objectViewer"
  member   = "serviceAccount:${google_service_account.runtime["worker"].email}"
}

resource "google_storage_bucket_iam_member" "worker_result_create" {
  bucket = google_storage_bucket.artifacts["results"].name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.runtime["worker"].email}"
  condition {
    # The worker publishes the manifest under manifests/ and result entries
    # under the reviewed result prefix, and nothing else in the bucket.
    title = "conditional_result_creation"
    expression = join(" || ", [
      "resource.name.startsWith(${jsonencode("projects/_/buckets/${google_storage_bucket.artifacts["results"].name}/objects/manifests/")})",
      "resource.name.startsWith(${jsonencode("projects/_/buckets/${google_storage_bucket.artifacts["results"].name}/objects/${var.result_prefix}")})",
    ])
  }
}

resource "google_storage_bucket_iam_member" "worker_result_read" {
  bucket = google_storage_bucket.artifacts["results"].name
  role   = google_project_iam_custom_role.result_reader.name
  member = "serviceAccount:${google_service_account.runtime["worker"].email}"
  condition {
    # Read-back is limited to the same two subtrees the worker may create in.
    title = "verify_existing_results"
    expression = join(" || ", [
      "resource.name.startsWith(${jsonencode("projects/_/buckets/${google_storage_bucket.artifacts["results"].name}/objects/manifests/")})",
      "resource.name.startsWith(${jsonencode("projects/_/buckets/${google_storage_bucket.artifacts["results"].name}/objects/${var.result_prefix}")})",
    ])
  }
}

# Batch reporting and log ingestion accept project-scoped grants. These grant
# no object deletion, job creation, IAM changes, or billing access to the worker.
resource "google_project_iam_member" "worker_reporting" {
  for_each = toset(["roles/batch.agentReporter", "roles/logging.logWriter"])
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.runtime["worker"].email}"
}

resource "google_artifact_registry_repository_iam_member" "worker_image" {
  project    = var.project_id
  location   = google_artifact_registry_repository.images.location
  repository = google_artifact_registry_repository.images.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.runtime["worker"].email}"
}

# Tasks' service agent mints task-caller tokens; the invoker identity itself
# receives no tokenCreator, application data, worker or Batch privileges.
resource "google_project_service_identity" "tasks" {
  provider   = google-beta
  project    = var.project_id
  service    = "cloudtasks.googleapis.com"
  depends_on = [google_project_service.required["cloudtasks.googleapis.com"]]
}

resource "google_project_iam_member" "tasks_service_agent" {
  project = var.project_id
  role    = "roles/cloudtasks.serviceAgent"
  member  = "serviceAccount:${google_project_service_identity.tasks.email}"
}

resource "google_project_service_identity" "scheduler" {
  provider   = google-beta
  project    = var.project_id
  service    = "cloudscheduler.googleapis.com"
  depends_on = [google_project_service.required["cloudscheduler.googleapis.com"]]
}

resource "google_project_iam_member" "scheduler_service_agent" {
  project = var.project_id
  role    = "roles/cloudscheduler.serviceAgent"
  member  = "serviceAccount:${google_project_service_identity.scheduler.email}"
}

resource "google_project_service_identity" "batch" {
  provider   = google-beta
  project    = var.project_id
  service    = "batch.googleapis.com"
  depends_on = [google_project_service.required["batch.googleapis.com"]]
}

resource "google_project_iam_member" "batch_service_agent" {
  project = var.project_id
  role    = "roles/batch.serviceAgent"
  member  = "serviceAccount:${google_project_service_identity.batch.email}"
}
