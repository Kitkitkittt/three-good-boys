# This API is an added deployment prerequisite, not an imported foundation API.
resource "google_project_service" "billing_budgets" {
  project            = var.project_id
  service            = "billingbudgets.googleapis.com"
  disable_on_destroy = false
}

resource "google_monitoring_notification_channel" "budget_email" {
  project      = var.project_id
  display_name = "LifeMate billing owner"
  type         = "email"
  labels = {
    email_address = var.budget_alert_email
  }
  enabled    = true
  depends_on = [google_project_service.required["monitoring.googleapis.com"]]
}

# Alerts are delayed signals, never an authorization to spend or a hard cap.
# Credit exclusion deliberately alerts on gross cost even while credits apply.
resource "google_billing_budget" "development" {
  billing_account = var.billing_account_id
  display_name    = "LifeMate approved development spend"
  budget_filter {
    projects               = ["projects/${data.google_project.selected.number}"]
    credit_types_treatment = "EXCLUDE_ALL_CREDITS"
    calendar_period        = "MONTH"
  }
  amount {
    specified_amount {
      currency_code = var.budget_currency
      units         = tostring(var.budget_amount)
    }
  }
  threshold_rules {
    threshold_percent = 0.5
    spend_basis       = "CURRENT_SPEND"
  }
  threshold_rules {
    threshold_percent = 0.9
    spend_basis       = "CURRENT_SPEND"
  }
  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "CURRENT_SPEND"
  }
  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "FORECASTED_SPEND"
  }
  all_updates_rule {
    monitoring_notification_channels = [google_monitoring_notification_channel.budget_email.name]
    disable_default_iam_recipients   = false
  }
  depends_on = [google_project_service.billing_budgets]
}
