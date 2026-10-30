resource "google_service_account" "runtime" {
  for_each = {
    web              = "sa-web"
    api              = "sa-api"
    dispatcher       = "sa-dispatcher"
    worker           = "sa-batch-worker"
    task_caller      = "sa-task-caller"
    scheduler_caller = "sa-scheduler-caller"
  }

  account_id   = each.value
  display_name = "LifeMate ${each.key}"

  depends_on = [google_project_service.required["iam.googleapis.com"]]
}
