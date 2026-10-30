# 13: Implement and review the Google Cloud foundation plan

**Parent spec:** [Shared Google Cloud platform #3](https://github.com/huyxdang/three-good-boys/issues/3).

**What to build:** Reviewable Terraform bootstrap/dev configurations for the existing approved project, private state/artifact storage, Artifact Registry, Firestore, dispatch queue and runtime identities. No model execution, billable workload or IAM/resource apply under this ticket.

**Blocked by:** None; project access and GPU quota have been observed.

**Status:** ready-for-agent

**Owner:** omp-cloud-foundation

**Progress:** done

## Acceptance criteria

- [x] Reuse the existing project; do not create projects, attach billing, replace default networks or grant Owner/Editor.
- [x] Separate state bootstrap from the dev foundation; versioned private state, no forced bucket deletion, explicit retention and no secrets in committed variables/state/plan.
- [x] Create only private artifact buckets, a regional Docker registry, regional Firestore, a conservative Cloud Tasks queue, and named runtime/caller identities. Do not deploy placeholder Cloud Run images or Scheduler targets before real handlers exist.
- [x] Keep existing enabled APIs on destroy; provision no GPU, VM, static IP, load balancer or standby capacity.
- [x] Expose project/region as reviewed inputs; validate identifiers and constrain the initial region to Singapore.
- [x] Validate and produce a real read-only plan in the authorized GCP Cloud Shell workspace; report all resources, no-op/existing API treatment, estimated recurring-cost categories and external approval gates.
- [x] Keep bootstrap/dev apply as a separate owner-reviewed operation; supply safe reproducible instructions and generated-file ignores.

## Verification

Verified in authorized Cloud Shell on 2026-10-30 using Terraform 1.13.5 and signed Google provider 6.50.0. Both roots passed formatting, locked initialization, validation and all eight retained rejection cases. Both generated provider lockfiles are committed. Two assertion-free positive cases were removed; valid inputs were exercised by the real plans.

The bootstrap plan proposed one state bucket. The backend-free dev preview proposed four artifact buckets, one Docker repository, one regional Firestore database, one queue and six service accounts: 13 additions plus 18 no-op imports of enabled APIs. Saved-plan JSON audit confirmed zero updates, deletions, replacements, IAM grants or compute workloads. Imported `disable_on_destroy` is serialized as null despite explicit false configuration; post-apply state verification remains with ticket 14. No apply or state adoption occurred.

Private evidence is retained in the authorized Cloud Shell account under `~/.local/share/lifemate-foundation-20261030/evidence/`: `bootstrap.tfplan`, `bootstrap-plan.json`, `dev-preview.tfplan` and `dev-preview-plan.json`. These are review evidence only, not approved apply inputs; obtain fresh canonical plans under ticket 14. Verification commands were `terraform fmt -check`, `init -backend=false -lockfile=readonly`, `validate`, `test`, real `plan -input=false -out=...` and `show -json` with a resource-action audit. Provider caches and previews remain outside the repository.

The [runbook](../../../docs/cloud-foundation.md#exercised-evidence--2026-10-30) records retention, cost categories, state migration, evidence limits and approval gates. Standards and spec reviews found no actionable findings in the cloud slice. Markdown verification resolved 30 local links across three pages; the README rendering was visually inspected. Persistent-resource/IAM apply, restricted artifact transfer and GPU execution remain unauthorized; this ticket completes the reviewed plan, not a deployment.

## Comments

The user selected project `project-cc6075c8-508b-491d-98d` and requested continuation after raising quota. Global GPU quota 1, Singapore L4 quota 1, both unused. Required APIs were enabled successfully before this ticket was created; Terraform must reconcile those idempotently. This ticket delivers the reviewed real plan; applying persistent resources and IAM belongs to ticket 14.

Read-only inventory after API enablement: no Firestore databases, Singapore Artifact Registry repositories or Singapore Cloud Tasks queues were observed. The existing default network and Compute service account are outside this ticket. Review actual bootstrap/dev plans and cost categories before considering ticket 13 complete; ticket 14 requires separate owner approval.
