mock_provider "google" {
  override_during = plan
  mock_data "google_project" {
    defaults = { number = "123456789012" }
  }
  mock_resource "google_project_service_identity" {
    defaults = { email = "service-123456789012@gcp-sa-iap.iam.gserviceaccount.com" }
  }
  mock_resource "google_service_account" {
    defaults = {
      email  = "sa-mock@test-project-123.iam.gserviceaccount.com"
      name   = "projects/test-project-123/serviceAccounts/sa-mock@test-project-123.iam.gserviceaccount.com"
      member = "serviceAccount:sa-mock@test-project-123.iam.gserviceaccount.com"
    }
  }
  mock_resource "google_project_iam_custom_role" {
    defaults = { name = "projects/test-project-123/roles/lifemateResultReader" }
  }
  mock_resource "google_artifact_registry_repository" {
    defaults = { name = "projects/test-project-123/locations/asia-southeast1/repositories/lifemate-images" }
  }
}

mock_provider "google-beta" {
  override_during = plan
  mock_data "google_project" {
    defaults = { number = "123456789012" }
  }
  mock_resource "google_project_service_identity" {
    defaults = { email = "service-123456789012@gcp-sa-iap.iam.gserviceaccount.com" }
  }
  mock_resource "google_service_account" {
    defaults = {
      email  = "sa-mock@test-project-123.iam.gserviceaccount.com"
      name   = "projects/test-project-123/serviceAccounts/sa-mock@test-project-123.iam.gserviceaccount.com"
      member = "serviceAccount:sa-mock@test-project-123.iam.gserviceaccount.com"
    }
  }
  mock_resource "google_project_iam_custom_role" {
    defaults = { name = "projects/test-project-123/roles/lifemateResultReader" }
  }
  mock_resource "google_artifact_registry_repository" {
    defaults = { name = "projects/test-project-123/locations/asia-southeast1/repositories/lifemate-images" }
  }
}

# Import blocks target existing services; tests must not contact Google APIs.
override_resource {
  target = google_project_service.required
}

variables {
  project_id         = "test-project-123"
  region             = "asia-southeast1"
  bucket_prefix      = "example-private-123"
  api_image_digest   = "asia-southeast1-docker.pkg.dev/test-project-123/lifemate-images/api@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  web_image_digest   = "asia-southeast1-docker.pkg.dev/test-project-123/lifemate-images/web@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  batch_image_digest = "asia-southeast1-docker.pkg.dev/test-project-123/lifemate-images/worker@sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
  api_roles = {
    "owner@example.com"  = "owner"
    "viewer@example.com" = "viewer"
  }
  api_catalog_json            = <<-JSON
  {
    "datasets": [{"id":"synthetic","hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","objects":{"data/input.json":"123"}}],
    "models": [{"id":"synthetic-model","hash":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","objects":{"models/model.json":"456"}}],
    "experiments": [{"id":"synthetic-experiment","benchmark_id":"synthetic-v1","cases":12,"content_hash":"dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd","mode":"agent","decoding":{},"expected_names":["predictions.jsonl"]}],
    "machine_type":"g2-standard-8","region":"asia-southeast1","timeout_seconds":600,"retry_allowance":0,
    "source_sha":"eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
    "image_digest":"asia-southeast1-docker.pkg.dev/test-project-123/lifemate-images/worker@sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
  }
  JSON
  batch_boot_disk_type        = "pd-balanced"
  batch_boot_disk_gb          = 100
  batch_arguments             = "/mnt/data/manifest.json --launcher /mnt/data/approved_launcher.py --pinned /mnt/data/pinned.json --run-dir /tmp/lifemate-worker"
  approved_input_prefix       = "data/"
  approved_model_prefix       = "models/"
  dispatcher_budget_cents     = 1000
  dispatcher_deadline_seconds = 1200
  result_prefix               = "runs/"
  api_result_prefixes         = ["runs/redacted/"]
  billing_account_id          = "ABCDEF-123456-ABCDEF"
  budget_amount               = 10
  budget_currency             = "USD"
  budget_alert_email          = "billing@example.com"
  github_repository           = "approved-owner/private-execution"
  github_repository_id        = "123456789"
  github_owner_id             = "987654321"
  github_branch               = "main"
  github_workflow             = "deploy-cloud.yml"
  github_environment          = "production"
}

run "reject_other_region" {
  command = plan
  variables {
    region = "us-central1"
  }
  expect_failures = [var.region]
}

run "reject_invalid_project" {
  command = plan
  variables {
    project_id = "Invalid_Project"
  }
  expect_failures = [var.project_id]
}

run "reject_reserved_bucket_prefix" {
  command = plan
  variables {
    bucket_prefix = "google-artifacts"
  }
  expect_failures = [var.bucket_prefix]
}

run "reject_prefix_that_makes_bucket_too_long" {
  command = plan
  variables {
    bucket_prefix = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  }
  expect_failures = [var.bucket_prefix]
}

run "private_services_and_direct_iap" {
  command = plan
  assert {
    condition = (
      !google_cloud_run_v2_service.api.invoker_iam_disabled &&
      !google_cloud_run_v2_service.dispatcher.invoker_iam_disabled &&
      !google_cloud_run_v2_service.web.invoker_iam_disabled &&
      google_cloud_run_v2_service.web.iap_enabled
    )
    error_message = "Web must use direct IAP; no service may bypass its Invoker IAM check."
  }
  assert {
    condition = (
      google_cloud_run_v2_service.api.ingress == "INGRESS_TRAFFIC_ALL" &&
      google_cloud_run_v2_service.dispatcher.ingress == "INGRESS_TRAFFIC_ALL" &&
      toset(google_cloud_run_v2_service_iam_binding.api_invoker.members) == toset(["serviceAccount:${google_service_account.runtime["web"].email}"]) &&
      toset(google_cloud_run_v2_service_iam_binding.dispatcher_invoker.members) == toset([
        "serviceAccount:${google_service_account.runtime["task_caller"].email}",
        "serviceAccount:${google_service_account.runtime["scheduler_caller"].email}",
      ]) &&
      toset(google_cloud_run_v2_service_iam_binding.web_invoker.members) == toset(["serviceAccount:${google_project_service_identity.iap.email}"])
    )
    error_message = "Reachable ingress must retain exact separate service identity allowlists, never allUsers or human machine invokers."
  }
  assert {
    condition = (
      toset(google_iap_web_cloud_run_service_iam_binding.team.members) == toset(["user:owner@example.com", "user:viewer@example.com"]) &&
      local.iap_audience == "/projects/123456789012/locations/asia-southeast1/services/lifemate-web"
    )
    error_message = "IAP access and signed assertion audience must match the approved frontend and application user list."
  }
  assert {
    condition = (
      google_cloud_run_v2_service.api.template[0].service_account == google_service_account.runtime["api"].email &&
      google_cloud_run_v2_service.dispatcher.template[0].service_account == google_service_account.runtime["dispatcher"].email &&
      google_cloud_run_v2_service.web.template[0].service_account == google_service_account.runtime["web"].email &&
      google_service_account.runtime["task_caller"].account_id == "sa-task-caller" &&
      google_service_account.runtime["worker"].account_id == "sa-batch-worker"
    )
    error_message = "Preserve and reuse the six existing foundation runtime identities."
  }
}

run "immutable_images_and_exact_runtime_config" {
  command = plan
  assert {
    condition = (
      google_cloud_run_v2_service.api.template[0].containers[0].image == var.api_image_digest &&
      google_cloud_run_v2_service.dispatcher.template[0].containers[0].image == var.api_image_digest &&
      google_cloud_run_v2_service.web.template[0].containers[0].image == var.web_image_digest &&
      google_cloud_run_v2_service.api.template[0].containers[0].args == tolist(["lifemate_api.server:app", "--factory", "--host", "0.0.0.0", "--port", "8080"]) &&
      google_cloud_run_v2_service.dispatcher.template[0].containers[0].args == tolist(["dispatcher.server:app", "--factory", "--host", "0.0.0.0", "--port", "8080"])
    )
    error_message = "API and dispatcher must reuse the approved immutable image with distinct real ASGI factories."
  }
  assert {
    condition = (
      toset([for item in google_cloud_run_v2_service.web.template[0].containers[0].env : item.name]) == toset(["LIFEMATE_API_URL", "LIFEMATE_API_AUDIENCE"]) &&
      local.api_env.LIFEMATE_DISPATCH_AUDIENCE == local.dispatcher_env.DISPATCH_AUDIENCE &&
      local.dispatcher_env.BATCH_IMAGE == jsondecode(var.api_catalog_json).image_digest &&
      local.dispatcher_env.BATCH_MACHINE_TYPE == jsondecode(var.api_catalog_json).machine_type &&
      local.dispatcher_env.TASK_TIMEOUT_SECONDS == tostring(jsondecode(var.api_catalog_json).timeout_seconds) &&
      local.dispatcher_env.BATCH_MAX_RETRIES == "0" &&
      local.dispatcher_env.TASK_SERVICE_ACCOUNT == google_service_account.runtime["task_caller"].email &&
      local.dispatcher_env.BATCH_SERVICE_ACCOUNT == google_service_account.runtime["worker"].email &&
      local.dispatcher_env.BATCH_MOUNTS == "example-private-123-data data /mnt/data ro;example-private-123-models models /mnt/models ro"
    )
    error_message = "Pass only consumed production config; tokens must be runtime metadata credentials, worker identity separate, policy consistent and inputs read-only."
  }
  assert {
    condition = alltrue([for service in [google_cloud_run_v2_service.api, google_cloud_run_v2_service.dispatcher, google_cloud_run_v2_service.web] :
      service.template[0].scaling[0].min_instance_count == 0 &&
      service.template[0].scaling[0].max_instance_count <= 2 && service.deletion_protection
    ])
    error_message = "Control-plane instances must scale to zero with bounded maximum instances and protected deletion."
  }
}

run "scheduler_uses_separate_oidc_identity" {
  command = plan
  assert {
    condition = (
      google_cloud_scheduler_job.reconcile.schedule == "* * * * *" &&
      google_cloud_scheduler_job.reconcile.http_target[0].uri == "${local.dispatcher_url}/internal/reconcile" &&
      google_cloud_scheduler_job.reconcile.http_target[0].oidc_token[0].service_account_email == google_service_account.runtime["scheduler_caller"].email &&
      google_cloud_scheduler_job.reconcile.http_target[0].oidc_token[0].audience == local.dispatcher_url &&
      google_cloud_scheduler_job.reconcile.retry_config[0].retry_count == 0
    )
    error_message = "Scheduler must reconcile regularly using its own authenticated invoker and path-free audience without immediate retry storms."
  }
}

run "least_privilege_resource_grants" {
  command = plan
  assert {
    condition = (
      toset(keys(google_project_iam_member.firestore)) == toset(["api", "dispatcher"]) &&
      alltrue([for grant in google_project_iam_member.firestore :
        grant.role == "roles/datastore.user" &&
        grant.condition[0].expression == "resource.name == \"projects/test-project-123/databases/(default)\""
      ]) &&
      toset(keys(google_cloud_tasks_queue_iam_member.enqueue)) == toset(["api", "dispatcher"]) &&
      alltrue([for grant in google_cloud_tasks_queue_iam_member.enqueue :
        grant.name == google_cloud_tasks_queue.dispatch.name && grant.role == "roles/cloudtasks.enqueuer"
      ]) &&
      google_service_account_iam_member.worker_act_as.service_account_id == google_service_account.runtime["worker"].name &&
      google_service_account_iam_member.worker_act_as.member == "serviceAccount:${google_service_account.runtime["dispatcher"].email}"
    )
    error_message = "Metadata, queue and act-as grants must stay on their exact database, queue and worker identity."
  }
  assert {
    condition = (
      toset(google_project_iam_custom_role.result_reader.permissions) == toset(["storage.objects.get"]) &&
      google_storage_bucket_iam_member.api_results.condition[0].expression == "resource.name.startsWith(\"projects/_/buckets/example-private-123-results/objects/runs/redacted/\")" &&
      google_storage_bucket_iam_member.dispatcher_results.role == google_project_iam_custom_role.result_reader.name &&
      google_storage_bucket_iam_member.dispatcher_results.condition[0].expression == join(" || ", [
        "resource.name.startsWith(\"projects/_/buckets/example-private-123-results/objects/manifests/\")",
        "resource.name.startsWith(\"projects/_/buckets/example-private-123-results/objects/runs/\")",
      ]) &&
      google_storage_bucket_iam_member.worker_result_create.role == "roles/storage.objectCreator" &&
      google_storage_bucket_iam_member.worker_result_create.condition[0].expression == join(" || ", [
        "resource.name.startsWith(\"projects/_/buckets/example-private-123-results/objects/manifests/\")",
        "resource.name.startsWith(\"projects/_/buckets/example-private-123-results/objects/runs/\")",
      ]) &&
      google_storage_bucket_iam_member.worker_result_read.role == google_project_iam_custom_role.result_reader.name &&
      google_storage_bucket_iam_member.worker_result_read.condition[0].expression == join(" || ", [
        "resource.name.startsWith(\"projects/_/buckets/example-private-123-results/objects/manifests/\")",
        "resource.name.startsWith(\"projects/_/buckets/example-private-123-results/objects/runs/\")",
      ]) &&
      toset(keys(google_storage_bucket_iam_member.worker_inputs)) == toset(["data", "models"])
    )
    error_message = "API reads only approved redacted metadata; dispatcher reads only manifests; worker creates and verifies under manifests and the run prefix, never whole-bucket."
  }
  assert {
    condition = (
      toset(google_project_iam_custom_role.dispatcher_batch.permissions) == toset(["batch.jobs.create", "batch.jobs.get", "batch.jobs.delete", "batch.operations.get", "batch.tasks.get", "batch.tasks.list"]) &&
      toset(keys(google_project_iam_member.worker_reporting)) == toset(["roles/batch.agentReporter", "roles/logging.logWriter"]) &&
      google_artifact_registry_repository_iam_member.worker_image.repository == google_artifact_registry_repository.images.name &&
      google_artifact_registry_repository_iam_member.worker_image.role == "roles/artifactregistry.reader"
    )
    error_message = "Batch lifecycle is custom minimal; worker gets reporting/logging and repository read, not job creation, billing or IAM administration."
  }
}

run "github_federation_is_exact_and_deploy_only" {
  command = plan
  assert {
    condition = (
      google_iam_workload_identity_pool_provider.github.oidc[0].issuer_uri == "https://token.actions.githubusercontent.com" &&
      google_iam_workload_identity_pool_provider.github.attribute_condition == join(" && ", [
        "assertion.repository_id == \"123456789\"",
        "assertion.repository_owner_id == \"987654321\"",
        "assertion.repository == \"approved-owner/private-execution\"",
        "assertion.ref == \"refs/heads/main\"",
        "assertion.ref_type == 'branch'",
        "assertion.ref_protected == 'true'",
        "assertion.workflow_ref == \"approved-owner/private-execution/.github/workflows/deploy-cloud.yml@refs/heads/main\"",
        "assertion.event_name == 'workflow_dispatch'",
        "assertion.environment == \"production\"",
        "assertion.sub == \"repo:approved-owner/private-execution:environment:production\"",
      ]) &&
      google_service_account_iam_member.github_deploy.service_account_id == google_service_account.ci["deploy"].name &&
      google_service_account_iam_member.github_deploy.role == "roles/iam.workloadIdentityUser"
    )
    error_message = "GitHub trust must pin numeric IDs plus exact repository/ref/workflow/manual event/protected environment and impersonate only the deployer."
  }
  assert {
    condition = (
      toset(keys(google_service_account_iam_member.ci_runtime_act_as)) == toset(["api", "dispatcher", "web"]) &&
      alltrue([for grant in google_cloud_run_v2_service_iam_member.ci_deploy : grant.role == "roles/run.developer"]) &&
      google_artifact_registry_repository_iam_member.ci_images["build"].role == "roles/artifactregistry.writer" &&
      google_artifact_registry_repository_iam_member.ci_images["deploy"].role == "roles/artifactregistry.reader"
    )
    error_message = "CI deployment must be service-scoped and unable to act as worker/task identities; build access is repository-only."
  }
}

run "budget_alert_is_scoped_gross_spend_not_hard_cap" {
  command = plan
  assert {
    condition = (
      google_billing_budget.development.billing_account == var.billing_account_id &&
      toset(google_billing_budget.development.budget_filter[0].projects) == toset(["projects/123456789012"]) &&
      google_billing_budget.development.budget_filter[0].credit_types_treatment == "EXCLUDE_ALL_CREDITS" &&
      google_billing_budget.development.amount[0].specified_amount[0].currency_code == "USD" &&
      tonumber(google_billing_budget.development.amount[0].specified_amount[0].units) == 10 &&
      toset([for rule in google_billing_budget.development.threshold_rules : rule.threshold_percent]) == toset([0.5, 0.9, 1]) &&
      google_monitoring_notification_channel.budget_email.labels.email_address == var.budget_alert_email
    )
    error_message = "Budget alerts must target the selected project's gross spend and explicit approved amount/currency/recipient."
  }
}

run "reject_mutable_api_image" {
  command = plan
  variables { api_image_digest = "asia-southeast1-docker.pkg.dev/test-project-123/lifemate-images/api:latest" }
  expect_failures = [var.api_image_digest]
}

run "reject_foreign_web_image" {
  command = plan
  variables { web_image_digest = "asia-southeast1-docker.pkg.dev/another-project/lifemate-images/web@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" }
  expect_failures = [var.web_image_digest]
}

run "reject_worker_catalog_image_mismatch" {
  command = plan
  variables { batch_image_digest = "asia-southeast1-docker.pkg.dev/test-project-123/lifemate-images/worker@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" }
  expect_failures = [var.batch_image_digest]
}

run "reject_roles_without_owner" {
  command = plan
  variables { api_roles = { "viewer@example.com" = "viewer" } }
  expect_failures = [var.api_roles]
}

run "reject_unregistered_role" {
  command = plan
  variables { api_roles = { "owner@example.com" = "Owner" } }
  expect_failures = [var.api_roles]
}

run "reject_empty_catalog" {
  command = plan
  variables { api_catalog_json = "{}" }
  expect_failures = [var.api_catalog_json]
}

run "reject_nonpositive_budget" {
  command = plan
  variables { dispatcher_budget_cents = 0 }
  expect_failures = [var.dispatcher_budget_cents]
}

run "reject_deadline_shorter_than_task" {
  command = plan
  variables { dispatcher_deadline_seconds = 300 }
  expect_failures = [var.dispatcher_deadline_seconds]
}

run "reject_unsafe_result_prefix" {
  command = plan
  variables { result_prefix = "../" }
  expect_failures = [var.result_prefix]
}

run "reject_bucket_wide_api_read" {
  command = plan
  variables { api_result_prefixes = ["runs/"] }
  expect_failures = [var.api_result_prefixes]
}

run "reject_unsupported_g2_disk" {
  command = plan
  variables { batch_boot_disk_type = "pd-standard" }
  expect_failures = [var.batch_boot_disk_type]
}

run "reject_shell_worker_arguments" {
  command = plan
  variables { batch_arguments = "sh -c echo unsafe; curl example.com" }
  expect_failures = [var.batch_arguments]
}

run "reject_non_numeric_github_identity" {
  command = plan
  variables { github_repository_id = "approved-owner/private-execution" }
  expect_failures = [var.github_repository_id]
}

run "reject_github_ref_instead_of_branch" {
  command = plan
  variables { github_branch = "refs/pull/1/merge" }
  expect_failures = [var.github_branch]
}

run "reject_workflow_path_injection" {
  command = plan
  variables { github_workflow = "../deploy.yml" }
  expect_failures = [var.github_workflow]
}

run "reject_missing_protected_environment" {
  command = plan
  variables { github_environment = "" }
  expect_failures = [var.github_environment]
}

run "reject_unapproved_billing_identifier" {
  command = plan
  variables { billing_account_id = "project-id-not-account" }
  expect_failures = [var.billing_account_id]
}

run "reject_zero_billing_alert" {
  command = plan
  variables { budget_amount = 0 }
  expect_failures = [var.budget_amount]
}

run "foundation_and_runtime_privileges_remain_bounded" {
  command = plan
  assert {
    condition = (
      toset(keys(google_service_account.runtime)) == toset(["web", "api", "dispatcher", "worker", "task_caller", "scheduler_caller"]) &&
      toset(keys(google_storage_bucket.artifacts)) == toset(["data", "models", "results", "release"]) &&
      alltrue([for bucket in google_storage_bucket.artifacts :
        bucket.uniform_bucket_level_access && bucket.public_access_prevention == "enforced" && !bucket.force_destroy
      ]) &&
      google_firestore_database.default.delete_protection_state == "DELETE_PROTECTION_ENABLED" &&
      google_artifact_registry_repository.images.docker_config[0].immutable_tags
    )
    error_message = "Preserve foundation identities and protected private storage, Firestore and immutable registry settings."
  }
  assert {
    condition = alltrue([for grant in concat(
      values(google_project_iam_member.firestore),
      values(google_project_iam_member.worker_reporting),
      [google_project_iam_member.dispatcher_batch, google_project_iam_member.tasks_service_agent, google_project_iam_member.scheduler_service_agent, google_project_iam_member.batch_service_agent],
    ) : !contains(["roles/owner", "roles/editor"], grant.role)])
    error_message = "No application, CI or service-agent identity may receive project-wide Owner or Editor."
  }
  assert {
    condition = (
      google_project_iam_member.tasks_service_agent.member == "serviceAccount:${google_project_service_identity.tasks.email}" &&
      google_project_iam_member.scheduler_service_agent.member == "serviceAccount:${google_project_service_identity.scheduler.email}" &&
      google_project_iam_member.batch_service_agent.member == "serviceAccount:${google_project_service_identity.batch.email}" &&
      !contains(keys(local.api_env), "LIFEMATE_API_ID_TOKEN") &&
      !contains(keys(local.dispatcher_env), "GOOGLE_APPLICATION_CREDENTIALS")
    )
    error_message = "Managed service-agent grants must not target runtimes, and production config must not carry static credentials."
  }
}

run "reject_unapproved_mount_prefix" {
  command = plan
  variables { approved_input_prefix = "/data/../private/" }
  expect_failures = [var.approved_input_prefix]
}

run "reject_unbounded_boot_disk" {
  command = plan
  variables { batch_boot_disk_gb = 1001 }
  expect_failures = [var.batch_boot_disk_gb]
}

run "reject_non_numeric_github_owner" {
  command = plan
  variables { github_owner_id = "approved-owner" }
  expect_failures = [var.github_owner_id]
}

run "reject_billing_currency_wildcard" {
  command = plan
  variables { budget_currency = "*" }
  expect_failures = [var.budget_currency]
}
