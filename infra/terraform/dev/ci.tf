resource "google_service_account" "ci" {
  for_each = {
    build  = "sa-ci-build"
    deploy = "sa-ci-deploy"
  }
  project      = var.project_id
  account_id   = each.value
  display_name = "LifeMate reviewed CI ${each.key}"
  depends_on   = [google_project_service.required["iam.googleapis.com"]]
}

resource "google_iam_workload_identity_pool" "github" {
  project                   = var.project_id
  workload_identity_pool_id = "lifemate-github"
  display_name              = "LifeMate protected GitHub deploy"
  disabled                  = false
  depends_on                = [google_project_service.required["iam.googleapis.com"]]
}

locals {
  github_workflow_ref = "${var.github_repository}/.github/workflows/${var.github_workflow}@refs/heads/${var.github_branch}"
  # Numeric IDs prevent repository/owner name takeover. ref, workflow, event,
  # environment and subject all match exactly; PR/fork tokens cannot qualify.
  github_condition = join(" && ", [
    "assertion.repository_id == ${jsonencode(var.github_repository_id)}",
    "assertion.repository_owner_id == ${jsonencode(var.github_owner_id)}",
    "assertion.repository == ${jsonencode(var.github_repository)}",
    "assertion.ref == ${jsonencode("refs/heads/${var.github_branch}")}",
    "assertion.ref_type == 'branch'",
    "assertion.ref_protected == 'true'",
    "assertion.workflow_ref == ${jsonencode(local.github_workflow_ref)}",
    "assertion.event_name == 'workflow_dispatch'",
    "assertion.environment == ${jsonencode(var.github_environment)}",
    "assertion.sub == ${jsonencode("repo:${var.github_repository}:environment:${var.github_environment}")}",
  ])
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "protected-deploy"
  display_name                       = "Exact reviewed manual deployment workflow"
  disabled                           = false
  attribute_mapping = {
    "google.subject"          = "assertion.sub"
    "attribute.repository_id" = "assertion.repository_id"
  }
  attribute_condition = local.github_condition
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_deploy" {
  service_account_id = google_service_account.ci["deploy"].name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository_id/${var.github_repository_id}"
}

# Routine deploy can update only these existing services, not create arbitrary
# services or change their IAM. Owner/bootstrap performs Terraform/IAP setup.
resource "google_cloud_run_v2_service_iam_member" "ci_deploy" {
  for_each = {
    api        = google_cloud_run_v2_service.api.name
    dispatcher = google_cloud_run_v2_service.dispatcher.name
    web        = google_cloud_run_v2_service.web.name
  }
  project  = var.project_id
  location = var.region
  name     = each.value
  role     = "roles/run.developer"
  member   = "serviceAccount:${google_service_account.ci["deploy"].email}"
}

resource "google_service_account_iam_member" "ci_runtime_act_as" {
  for_each           = toset(["web", "api", "dispatcher"])
  service_account_id = google_service_account.runtime[each.key].name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.ci["deploy"].email}"
}

resource "google_artifact_registry_repository_iam_member" "ci_images" {
  for_each = {
    build  = "roles/artifactregistry.writer"
    deploy = "roles/artifactregistry.reader"
  }
  project    = var.project_id
  location   = google_artifact_registry_repository.images.location
  repository = google_artifact_registry_repository.images.name
  role       = each.value
  member     = "serviceAccount:${google_service_account.ci[each.key].email}"
}

# No WIF impersonation or build-submission/source-data grants to sa-ci-build:
# the private build workspace/source approval is a separate prerequisite. Do
# not give the deployment workflow access to restricted data by implication.
