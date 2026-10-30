data "google_project" "selected" {
  project_id = var.project_id
}

locals {
  service_names = {
    api        = "lifemate-api"
    web        = "lifemate-web"
    dispatcher = "lifemate-dispatcher"
  }
  # Cloud Run's documented deterministic URL avoids a service referencing its
  # own computed uri through DISPATCH_URL. Keep the token audience path-free.
  dispatcher_url = "https://${local.service_names.dispatcher}-${data.google_project.selected.number}.${var.region}.run.app"
  iap_audience   = "/projects/${data.google_project.selected.number}/locations/${var.region}/services/${local.service_names.web}"
  catalog        = try(jsondecode(var.api_catalog_json), {})

  api_env = {
    GOOGLE_CLOUD_PROJECT        = var.project_id
    LIFEMATE_FIRESTORE_DATABASE = google_firestore_database.default.name
    LIFEMATE_IAP_AUDIENCE       = local.iap_audience
    LIFEMATE_ROLES              = jsonencode(var.api_roles)
    LIFEMATE_CATALOG            = var.api_catalog_json
    LIFEMATE_DISPATCH_URL       = "${local.dispatcher_url}/internal/dispatch"
    LIFEMATE_DISPATCH_AUDIENCE  = local.dispatcher_url
    LIFEMATE_TASKS_QUEUE        = google_cloud_tasks_queue.dispatch.name
    LIFEMATE_TASKS_LOCATION     = google_cloud_tasks_queue.dispatch.location
    LIFEMATE_TASKS_SA           = google_service_account.runtime["task_caller"].email
  }
  dispatcher_env = {
    PROJECT_ID            = var.project_id
    FIRESTORE_DATABASE    = google_firestore_database.default.name
    REGION                = var.region
    DISPATCH_URL          = "${local.dispatcher_url}/internal/dispatch"
    TASK_SERVICE_ACCOUNT  = google_service_account.runtime["task_caller"].email
    DISPATCH_AUDIENCE     = local.dispatcher_url
    TASKS_LOCATION        = google_cloud_tasks_queue.dispatch.location
    TASKS_QUEUE           = google_cloud_tasks_queue.dispatch.name
    RESULTS_BUCKET        = google_storage_bucket.artifacts["results"].name
    RESULT_PREFIX         = var.result_prefix
    BUDGET_CENTS          = tostring(var.dispatcher_budget_cents)
    DEADLINE_SECONDS      = tostring(var.dispatcher_deadline_seconds)
    BATCH_IMAGE           = var.batch_image_digest
    BATCH_SERVICE_ACCOUNT = google_service_account.runtime["worker"].email
    BATCH_MACHINE_TYPE    = try(local.catalog.machine_type, "")
    BATCH_BOOT_DISK_TYPE  = var.batch_boot_disk_type
    BATCH_BOOT_DISK_GB    = tostring(var.batch_boot_disk_gb)
    TASK_TIMEOUT_SECONDS  = tostring(try(local.catalog.timeout_seconds, 0))
    BATCH_MAX_RETRIES     = tostring(try(local.catalog.retry_allowance, 0))
    BATCH_ARGUMENTS       = var.batch_arguments
    BATCH_MOUNTS = join(";", [
      "${google_storage_bucket.artifacts["data"].name} ${trimsuffix(var.approved_input_prefix, "/")} /mnt/data ro",
      "${google_storage_bucket.artifacts["models"].name} ${trimsuffix(var.approved_model_prefix, "/")} /mnt/models ro",
    ])
  }
}

resource "google_cloud_run_v2_service" "api" {
  project              = var.project_id
  name                 = local.service_names.api
  location             = var.region
  ingress              = "INGRESS_TRAFFIC_ALL"
  invoker_iam_disabled = false
  deletion_protection  = true

  template {
    service_account                  = google_service_account.runtime["api"].email
    timeout                          = "60s"
    max_instance_request_concurrency = 40
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
    containers {
      image   = var.api_image_digest
      command = ["uvicorn"]
      args    = ["lifemate_api.server:app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
      ports {
        container_port = 8080
      }
      resources {
        limits   = { cpu = "1", memory = "512Mi" }
        cpu_idle = true
      }
      dynamic "env" {
        for_each = local.api_env
        content {
          name  = env.key
          value = env.value
        }
      }
      startup_probe {
        http_get {
          path = "/healthz"
          port = 8080
        }
      }
    }
  }
  depends_on = [
    google_project_service.required["run.googleapis.com"],
    google_project_iam_member.firestore,
    google_cloud_tasks_queue_iam_member.enqueue,
    google_service_account_iam_member.task_act_as,
    google_storage_bucket_iam_member.api_results,
    google_project_iam_member.tasks_service_agent,
  ]
}

resource "google_cloud_run_v2_service" "dispatcher" {
  project              = var.project_id
  name                 = local.service_names.dispatcher
  location             = var.region
  ingress              = "INGRESS_TRAFFIC_ALL"
  invoker_iam_disabled = false
  custom_audiences     = [local.dispatcher_url]
  deletion_protection  = true

  template {
    service_account                  = google_service_account.runtime["dispatcher"].email
    timeout                          = "300s"
    max_instance_request_concurrency = 1
    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }
    containers {
      image   = var.api_image_digest
      command = ["uvicorn"]
      args    = ["dispatcher.server:app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
      ports {
        container_port = 8080
      }
      resources {
        limits   = { cpu = "1", memory = "512Mi" }
        cpu_idle = true
      }
      dynamic "env" {
        for_each = local.dispatcher_env
        content {
          name  = env.key
          value = env.value
        }
      }
      startup_probe {
        http_get {
          path = "/healthz"
          port = 8080
        }
      }
    }
  }
  depends_on = [
    google_project_service.required["run.googleapis.com"],
    google_project_iam_member.firestore,
    google_project_iam_member.dispatcher_batch,
    google_cloud_tasks_queue_iam_member.enqueue,
    google_service_account_iam_member.task_act_as,
    google_service_account_iam_member.worker_act_as,
    google_storage_bucket_iam_member.dispatcher_results,
    google_project_iam_member.tasks_service_agent,
    google_project_iam_member.batch_service_agent,
    google_project_iam_member.worker_reporting,
    google_storage_bucket_iam_member.worker_inputs,
    google_storage_bucket_iam_member.worker_result_create,
    google_storage_bucket_iam_member.worker_result_read,
    google_artifact_registry_repository_iam_member.worker_image,
  ]
}

resource "google_cloud_run_v2_service" "web" {
  provider             = google-beta
  project              = var.project_id
  name                 = local.service_names.web
  location             = var.region
  launch_stage         = "BETA"
  ingress              = "INGRESS_TRAFFIC_ALL"
  iap_enabled          = true
  invoker_iam_disabled = false
  deletion_protection  = true

  template {
    service_account                  = google_service_account.runtime["web"].email
    timeout                          = "60s"
    max_instance_request_concurrency = 40
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
    containers {
      image = var.web_image_digest
      # The immutable web image starts the standalone Next.js server; no shell
      # override or build-time credentials are needed.
      ports {
        container_port = 8080
      }
      resources {
        limits   = { cpu = "1", memory = "512Mi" }
        cpu_idle = true
      }
      env {
        name  = "LIFEMATE_API_URL"
        value = google_cloud_run_v2_service.api.uri
      }
      env {
        name  = "LIFEMATE_API_AUDIENCE"
        value = google_cloud_run_v2_service.api.uri
      }
    }
  }
  depends_on = [
    google_project_service.required["run.googleapis.com"],
    google_project_service.required["iap.googleapis.com"],
    google_cloud_run_v2_service_iam_binding.api_invoker,
  ]
}

# Authentication, not network ingress, makes the API and dispatcher private.
# Tasks, Scheduler and web can reach run.app without a VPC/NAT deployment.
resource "google_cloud_run_v2_service_iam_binding" "api_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  members  = ["serviceAccount:${google_service_account.runtime["web"].email}"]
}

resource "google_cloud_run_v2_service_iam_binding" "dispatcher_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.dispatcher.name
  role     = "roles/run.invoker"
  members = [
    "serviceAccount:${google_service_account.runtime["task_caller"].email}",
    "serviceAccount:${google_service_account.runtime["scheduler_caller"].email}",
  ]
}

resource "google_project_service_identity" "iap" {
  provider   = google-beta
  project    = var.project_id
  service    = "iap.googleapis.com"
  depends_on = [google_project_service.required["iap.googleapis.com"]]
}

resource "google_cloud_run_v2_service_iam_binding" "web_invoker" {
  provider = google-beta
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.web.name
  role     = "roles/run.invoker"
  members  = ["serviceAccount:${google_project_service_identity.iap.email}"]
}

resource "google_iap_web_cloud_run_service_iam_binding" "team" {
  provider               = google-beta
  project                = var.project_id
  location               = var.region
  cloud_run_service_name = google_cloud_run_v2_service.web.name
  role                   = "roles/iap.httpsResourceAccessor"
  members                = [for email in sort(keys(var.api_roles)) : "user:${email}"]
}

resource "google_cloud_scheduler_job" "reconcile" {
  project          = var.project_id
  name             = "lifemate-reconcile"
  region           = var.region
  description      = "Repair durable dispatch intent and reconcile Batch outcomes; no GPU is scheduled by Terraform."
  schedule         = "* * * * *"
  time_zone        = "Etc/UTC"
  attempt_deadline = "300s"
  retry_config {
    retry_count          = 0
    max_retry_duration   = "0s"
    min_backoff_duration = "5s"
    max_backoff_duration = "60s"
    max_doublings        = 0
  }
  http_target {
    http_method = "POST"
    uri         = "${local.dispatcher_url}/internal/reconcile"
    body        = base64encode("{}")
    headers     = { "Content-Type" = "application/json" }
    oidc_token {
      service_account_email = google_service_account.runtime["scheduler_caller"].email
      audience              = local.dispatcher_url
    }
  }
  depends_on = [
    google_project_service.required["cloudscheduler.googleapis.com"],
    google_cloud_run_v2_service_iam_binding.dispatcher_invoker,
    google_project_iam_member.scheduler_service_agent,
  ]
}
