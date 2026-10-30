variable "api_image_digest" {
  description = "Approved API image, also used by the dispatcher; immutable digest in this project's private repository."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^${var.region}-docker[.]pkg[.]dev/${var.project_id}/lifemate-images/[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$", var.api_image_digest))
    error_message = "api_image_digest must pin sha256 in the selected project's regional lifemate-images repository."
  }
}

variable "web_image_digest" {
  description = "Approved standalone Next.js image at an immutable digest in this project's private repository."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^${var.region}-docker[.]pkg[.]dev/${var.project_id}/lifemate-images/[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$", var.web_image_digest))
    error_message = "web_image_digest must pin sha256 in the selected project's regional lifemate-images repository."
  }
}

variable "batch_image_digest" {
  description = "Approved worker image digest; must match the same immutable policy in api_catalog_json."
  type        = string
  nullable    = false
  validation {
    condition = (
      can(regex("^${var.region}-docker[.]pkg[.]dev/${var.project_id}/lifemate-images/[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$", var.batch_image_digest)) &&
      try(var.batch_image_digest == jsondecode(var.api_catalog_json).image_digest, false)
    )
    error_message = "batch_image_digest must pin this project's private image and equal api_catalog_json.image_digest."
  }
}

variable "batch_boot_disk_type" {
  description = "Explicit approved G2-compatible boot disk type."
  type        = string
  nullable    = false
  validation {
    condition     = contains(["pd-balanced", "pd-ssd"], var.batch_boot_disk_type)
    error_message = "batch_boot_disk_type must be pd-balanced or pd-ssd, never unsupported pd-standard."
  }
}

variable "batch_boot_disk_gb" {
  description = "Explicit approved boot/scratch disk size including immutable image and local checkpoint headroom."
  type        = number
  nullable    = false
  validation {
    condition     = var.batch_boot_disk_gb >= 50 && var.batch_boot_disk_gb <= 1000 && floor(var.batch_boot_disk_gb) == var.batch_boot_disk_gb
    error_message = "batch_boot_disk_gb must be an approved integer from 50 to 1000 GiB."
  }
}

variable "batch_arguments" {
  description = "Explicit reviewed Batch container arguments (appended to the worker image ENTRYPOINT), whitespace-separated without shell/quotes. Include approved manifest/launcher/pinned identities and local scratch path; no fabricated official launcher default or secrets."
  type        = string
  nullable    = false
  validation {
    condition = (
      length(trimspace(var.batch_arguments)) > 0 && length(var.batch_arguments) <= 4096 &&
      !can(regex("[\\n\\r'\"`;$|&<>]", var.batch_arguments))
    )
    error_message = "batch_arguments must be explicit single-line plain argv without shell syntax, quotes or inline secrets."
  }
}

variable "approved_input_prefix" {
  description = "Approved read-only data-bucket prefix mounted under /mnt/data; authorization to upload restricted data remains separate."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^[a-zA-Z0-9_-]+(/[a-zA-Z0-9_-]+)*/$", var.approved_input_prefix))
    error_message = "approved_input_prefix must be a safe nonempty slash-terminated object prefix."
  }
}

variable "approved_model_prefix" {
  description = "Approved read-only model-bucket prefix mounted under /mnt/models."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^[a-zA-Z0-9_-]+(/[a-zA-Z0-9_-]+)*/$", var.approved_model_prefix))
    error_message = "approved_model_prefix must be a safe nonempty slash-terminated object prefix."
  }
}

variable "api_roles" {
  description = "Approved Google user emails and application roles; the same explicit users receive web IAP access. Stored in Terraform state, not a secret store."
  type        = map(string)
  nullable    = false
  validation {
    condition = (
      length(var.api_roles) > 0 && contains(values(var.api_roles), "owner") &&
      alltrue([for email, role in var.api_roles :
        can(regex("^[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9.-]+[.][a-z]{2,}$", email)) &&
        contains(["owner", "maintainer", "researcher", "viewer"], role)
      ])
    )
    error_message = "api_roles requires lowercase Google user emails, supported application roles and at least one owner."
  }
}

variable "api_catalog_json" {
  description = "Owner-approved LIFEMATE_CATALOG JSON: datasets/models with sha256 hashes and pinned object generations, experiments and immutable worker policy. No payloads, evaluation labels, tokens or secrets."
  type        = string
  nullable    = false
  validation {
    condition = try(
      length(jsondecode(var.api_catalog_json).datasets) > 0 &&
      length(jsondecode(var.api_catalog_json).models) > 0 &&
      length(jsondecode(var.api_catalog_json).experiments) > 0 &&
      contains(["g2-standard-4", "g2-standard-8", "g2-standard-16"], jsondecode(var.api_catalog_json).machine_type) &&
      jsondecode(var.api_catalog_json).region == var.region &&
      jsondecode(var.api_catalog_json).timeout_seconds >= 60 &&
      jsondecode(var.api_catalog_json).timeout_seconds <= 86400 &&
      floor(jsondecode(var.api_catalog_json).timeout_seconds) == jsondecode(var.api_catalog_json).timeout_seconds &&
      jsondecode(var.api_catalog_json).retry_allowance == 0 &&
      can(regex("^[0-9a-f]{40}$", jsondecode(var.api_catalog_json).source_sha)) &&
      can(regex("^${var.region}-docker[.]pkg[.]dev/${var.project_id}/lifemate-images/[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$", jsondecode(var.api_catalog_json).image_digest)) &&
      alltrue([for item in concat(jsondecode(var.api_catalog_json).datasets, jsondecode(var.api_catalog_json).models) :
        can(regex("^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$", item.id)) &&
        can(regex("^[0-9a-f]{64}$", item.hash)) && length(item.objects) > 0 &&
        alltrue([for name, generation in item.objects :
          can(regex("^[a-zA-Z0-9][a-zA-Z0-9._/-]*$", name)) &&
          !can(regex("[.][.]|//", name)) &&
          can(regex("^[1-9][0-9]*$", tostring(generation)))
        ])
      ]) &&
      alltrue([for item in jsondecode(var.api_catalog_json).experiments :
        can(regex("^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$", item.id)) &&
        length(item.benchmark_id) > 0 && item.cases > 0 && floor(item.cases) == item.cases &&
        can(regex("^[0-9a-f]{64}$", item.content_hash)) &&
        can(regex("^[a-zA-Z0-9_-]+$", item.mode)) &&
        length(item.expected_names) > 0 &&
        length(distinct(item.expected_names)) == length(item.expected_names) &&
        alltrue([for name in item.expected_names :
          can(regex("^[a-zA-Z0-9][a-zA-Z0-9._/-]*$", name)) && !can(regex("[.][.]|//", name))
        ])
      ]) &&
      length(distinct([for item in jsondecode(var.api_catalog_json).datasets : item.id])) == length(jsondecode(var.api_catalog_json).datasets) &&
      length(distinct([for item in jsondecode(var.api_catalog_json).models : item.id])) == length(jsondecode(var.api_catalog_json).models) &&
      length(distinct([for item in jsondecode(var.api_catalog_json).experiments : item.id])) == length(jsondecode(var.api_catalog_json).experiments),
      false
    )
    error_message = "api_catalog_json must contain unique approved artifact/experiment IDs, sha256 hashes, safe relative object names with pinned generations, exact source/image pins, Singapore G2 policy, 60-86400s timeout and zero retries until SDK recovery is approved."
  }
}

variable "dispatcher_budget_cents" {
  description = "Explicit owner-approved application reservation ceiling in cents; not a billing hard cap or verified credit balance."
  type        = number
  nullable    = false
  validation {
    condition     = var.dispatcher_budget_cents > 0 && floor(var.dispatcher_budget_cents) == var.dispatcher_budget_cents
    error_message = "dispatcher_budget_cents must be an explicitly approved positive integer."
  }
}

variable "dispatcher_deadline_seconds" {
  description = "Whole-run reconciliation deadline including startup/loading/cleanup, explicitly approved independently of task timeout."
  type        = number
  nullable    = false
  validation {
    condition = (
      var.dispatcher_deadline_seconds >= 60 && var.dispatcher_deadline_seconds <= 172800 &&
      floor(var.dispatcher_deadline_seconds) == var.dispatcher_deadline_seconds &&
      try(var.dispatcher_deadline_seconds > jsondecode(var.api_catalog_json).timeout_seconds, false)
    )
    error_message = "dispatcher_deadline_seconds must be an integer <=172800 and greater than the approved catalog task timeout."
  }
}

variable "result_prefix" {
  description = "Approved result object prefix for worker writes and dispatcher verification; no leading slash, traversal or bucket-wide access."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^[a-zA-Z0-9_-]+(/[a-zA-Z0-9_-]+)*/$", var.result_prefix))
    error_message = "result_prefix must be a nonempty slash-terminated path of letters, digits, underscores or hyphens."
  }
}

variable "api_result_prefixes" {
  description = "Approved redacted user-visible metadata prefixes beneath result_prefix; API gets object-read only, never list/write/input access."
  type        = set(string)
  nullable    = false
  validation {
    condition = length(var.api_result_prefixes) > 0 && alltrue([for prefix in var.api_result_prefixes :
      can(regex("^[a-zA-Z0-9_-]+(/[a-zA-Z0-9_-]+)*/$", prefix)) &&
      startswith(prefix, var.result_prefix) && prefix != var.result_prefix
    ])
    error_message = "api_result_prefixes must be explicit safe child prefixes of result_prefix (not the whole results subtree)."
  }
}

variable "billing_account_id" {
  description = "Owner-approved existing billing account for alerting only; no billing association or upgrade is managed."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^[A-F0-9]{6}-[A-F0-9]{6}-[A-F0-9]{6}$", var.billing_account_id))
    error_message = "billing_account_id must use the XXXXXX-XXXXXX-XXXXXX billing account format."
  }
}

variable "budget_amount" {
  description = "Explicit monthly billing alert amount in budget_currency; excludes credits so alerts show gross spend, not a hard cap."
  type        = number
  nullable    = false
  validation {
    condition     = var.budget_amount > 0 && floor(var.budget_amount) == var.budget_amount
    error_message = "budget_amount must be an explicitly approved positive whole currency amount."
  }
}

variable "budget_currency" {
  description = "Verified billing account ISO-4217 currency. API checks account compatibility at apply."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^[A-Z]{3}$", var.budget_currency))
    error_message = "budget_currency must be a three-letter uppercase currency code."
  }
}

variable "budget_alert_email" {
  description = "Owner-approved monitored email destination for billing alerts."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^[^@\n\r ]+@[^@\n\r ]+[.][a-zA-Z]{2,}$", var.budget_alert_email))
    error_message = "budget_alert_email must be an explicit email address."
  }
}

variable "github_repository" {
  description = "Approved private/protected execution repository owner/name; numeric claims are checked separately."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^[a-zA-Z0-9][a-zA-Z0-9-]*/[a-zA-Z0-9_.-]+$", var.github_repository))
    error_message = "github_repository must name exactly one owner/repository."
  }
}

variable "github_repository_id" {
  description = "Verified actual numeric GitHub repository ID, not its mutable name."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^[1-9][0-9]*$", var.github_repository_id))
    error_message = "github_repository_id must be the verified numeric repository ID."
  }
}

variable "github_owner_id" {
  description = "Verified actual numeric GitHub repository owner ID."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^[1-9][0-9]*$", var.github_owner_id))
    error_message = "github_owner_id must be the verified numeric owner ID."
  }
}

variable "github_branch" {
  description = "Exact protected deployment branch (not a ref, tag, wildcard or pull-request merge ref)."
  type        = string
  nullable    = false
  validation {
    condition = (
      can(regex("^[a-zA-Z0-9][a-zA-Z0-9._/-]*[a-zA-Z0-9_-]$", var.github_branch)) &&
      !can(regex("[.][.]|//|[.]lock(/|$)", var.github_branch)) && !startswith(var.github_branch, "refs/")
    )
    error_message = "github_branch must name one exact valid protected branch without refs/, traversal or wildcards."
  }
}

variable "github_workflow" {
  description = "Exact workflow file under .github/workflows allowed to request deployment credentials."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^[a-zA-Z0-9_-][a-zA-Z0-9_.-]*[.]ya?ml$", var.github_workflow))
    error_message = "github_workflow must be a single named YAML workflow file, without directories or wildcards."
  }
}

variable "github_environment" {
  description = "Exact protected GitHub environment with owner-configured required reviewers and branch restrictions (Terraform cannot verify those controls)."
  type        = string
  nullable    = false
  validation {
    condition     = can(regex("^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$", var.github_environment))
    error_message = "github_environment must be an explicit safe environment name."
  }
}
