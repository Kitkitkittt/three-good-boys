terraform {
  required_version = ">= 1.10.0, < 2.0.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "= 6.50.0"
    }
  }
}

provider "google" {
  project               = var.project_id
  region                = var.region
  billing_project       = var.project_id
  user_project_override = true
}

variable "project_id" {
  description = "Existing, explicitly approved Google Cloud project ID."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "project_id must be a 6-30 character lowercase Google Cloud project ID."
  }
}

variable "region" {
  description = "Approved region for the state bucket."
  type        = string
  nullable    = false

  validation {
    condition     = var.region == "asia-southeast1"
    error_message = "The initial foundation is restricted to asia-southeast1."
  }
}

variable "state_bucket_name" {
  description = "Globally unique, non-sensitive state bucket name, selected by the operator."
  type        = string
  nullable    = false

  validation {
    condition = (
      can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", var.state_bucket_name)) &&
      !startswith(var.state_bucket_name, "goog") &&
      !can(regex("g[o0]{2}g[l1]e", var.state_bucket_name))
    )
    error_message = "state_bucket_name must be 3-63 lowercase letters, digits or hyphens, start and end with a letter or digit, and not use a Google-reserved name."
  }
}

resource "google_storage_bucket" "state" {
  name                        = var.state_bucket_name
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  # Keep the current state indefinitely; remove versions 30 days after replacement.
  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      with_state                 = "ARCHIVED"
      days_since_noncurrent_time = 30
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

output "state_bucket_name" {
  description = "Bucket for independently prefixed bootstrap and dev state."
  value       = google_storage_bucket.state.name
}
