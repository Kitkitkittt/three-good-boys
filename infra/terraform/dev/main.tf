terraform {
  required_version = ">= 1.10.0, < 2.0.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "= 6.50.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
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

# Direct Cloud Run IAP is beta in the pinned 6.50 provider.
provider "google-beta" {
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
  description = "Approved region for all regional foundation resources."
  type        = string
  nullable    = false

  validation {
    condition     = var.region == "asia-southeast1"
    error_message = "The initial foundation is restricted to asia-southeast1."
  }
}

variable "bucket_prefix" {
  description = "Non-sensitive, globally unique prefix for the four artifact bucket names."
  type        = string
  nullable    = false

  validation {
    condition = (
      can(regex("^[a-z0-9][a-z0-9-]{0,53}[a-z0-9]$", var.bucket_prefix)) &&
      !startswith(var.bucket_prefix, "goog") &&
      !can(regex("g[o0]{2}g[l1]e", var.bucket_prefix))
    )
    error_message = "bucket_prefix must be 2-55 lowercase letters, digits or hyphens, start and end with a letter or digit, and not use a Google-reserved name."
  }
}
