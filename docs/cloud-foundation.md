# Google Cloud foundation: review, state and apply

This configuration is **not deployment evidence or permission to apply**. Ticket 13 is complete only after Cloud Shell validation and a real read-only plan; ticket 14 separately requires explicit owner approval for persistent resources, IAM, retention and spending. The [implementation plan](google-cloud-implementation-plan.md) and [local ticket](../.scratch/lifemate/issues/13-google-cloud-foundation-plan.md) remain authoritative. All checks and builds run in the approved Google Cloud workspace, not public runners.

## Resource and IAM review

| Configuration | Intended resource and safeguards |
| --- | --- |
| `bootstrap` | One Singapore Standard state bucket, uniform bucket-level access, public access prevention, object versioning, `force_destroy = false` and Terraform `prevent_destroy`. The current state has no age expiry; noncurrent state versions are deleted 30 days after becoming noncurrent, subject to GCS soft-delete behavior. Access uses existing project/bucket IAM; no grants are created here. |
| `dev/services.tf` | Declaratively import the 18 APIs enabled by the coordinator: Artifact Registry, Batch, Cloud Build, Cloud Resource Manager, Cloud Scheduler, Cloud Tasks, Cloud Trace, Compute, Firestore, IAM, IAM Credentials, IAP, Logging, Monitoring, Cloud Run, Secret Manager, Cloud Storage and Security Token Service. `disable_on_destroy = false` leaves them enabled. Importing an enabled service may appear as an in-place change to this Terraform-only deletion flag; this is not a new API enablement. Stop for review if an expected service is missing or a plan proposes service enablement/disablement. |
| `dev/storage.tf` | Four separate Standard buckets for data, models, results and release, with public access prevention, uniform access, `force_destroy = false` and `prevent_destroy`. Only **incomplete multipart uploads** older than seven days are aborted. No completed input, model, result or release object is expired automatically. Results and release retention/export remain operator responsibilities. |
| `dev/registry.tf` | Private regional Docker repository with immutable tags. Untagged images older than 30 days are eligible for deletion; tagged releases are not matched by this policy. Artifact Registry runs cleanup asynchronously; a digest with its tag removed becomes eligible once it is old enough. Preserve and externally back up approved release digests. |
| `dev/firestore.tf` | One regional Native-mode `(default)` Firestore database, Google-side deletion protection, `deletion_policy = "ABANDON"` and Terraform `prevent_destroy`. The location is immutable. Never replace or import an existing default database without first reconciling its mode, location, data and ownership. |
| `dev/queue.tf` | A regional dispatch queue: one concurrent HTTP dispatch, one dispatch/second, five configured attempts, a five-minute retry duration and 10–300 second exponential backoff. Cloud Tasks requires both the attempts and duration conditions to be met before it stops retrying, so neither value is a strict standalone upper bound. Review the retry semantics before accepting task producers. Queue concurrency does **not** limit a running Batch job: the future dispatcher must retain a Firestore admission slot through terminal reconciliation. No target is configured. |
| `dev/identity.tf` | Six distinct service accounts: `sa-web`, `sa-api`, `sa-dispatcher`, `sa-batch-worker`, `sa-task-caller` and `sa-scheduler-caller`. They are identities only; **no IAM role bindings or service-account keys** are created. Existing inherited project grants are not altered or claimed absent. |

No project, billing attachment, IAM binding, default service-account policy, network, VM, GPU, IP, load balancer, Cloud Run placeholder, Scheduler job/URL or workload identity federation is managed. Google-managed service agents are not application identities. Creating a service account alone does not authorize an application: before any real service, separately review the scoped candidate capabilities in [the implementation plan](google-cloud-implementation-plan.md#5-iam-and-deployment-controls), including resource-level Cloud Run invocation, queue enqueue, service-account `actAs`, approved bucket reads/writes, Firestore and Batch access. No Owner/Editor grant or blanket project IAM change is proposed. The bootstrap operator needs sufficient existing permissions for the reviewed plan/apply and state bucket; no broad grants are implied.

Expect costs for live/noncurrent/soft-deleted GCS storage, operations and egress; Artifact Registry storage and transfer; Firestore storage, indexes and operations; Cloud Tasks requests; and logs/API usage if later enabled by clients. Current prices, eligible credits and ongoing costs must be checked for this project and region; budget alerts are not hard spending caps. Empty or idle does not guarantee zero cost.

## Inputs and authentication

Terraform `>= 1.10.0, < 2.0.0` and Google provider `6.50.0` are specified in both roots. Both committed `.terraform.lock.hcl` files were generated by Terraform in authorized Cloud Shell; preserve them and review any provider upgrade. Run checks with `TF_DATA_DIR` and provider/plugin caches outside the repository; for multiple roots use a distinct data directory per root. Plan and state files belong in a restricted workspace outside the repository. Choose inputs explicitly rather than committing real account IDs or email addresses:

```sh
export TF_VAR_project_id='<approved-existing-project-id>'
export TF_VAR_region='asia-southeast1'
export TF_VAR_state_bucket_name='<globally-unique-state-bucket>'
export TF_VAR_bucket_prefix='<globally-unique-artifact-prefix>'
```

Bucket names are public and globally unique: use non-sensitive random names, not a user, project ID, project number, email or credential. The artifact prefix produces `-data`, `-models`, `-results`, and `-release`; it is limited to 55 characters so every generated bucket name fits 63 characters. Restricted Google names, dots and invalid characters are rejected, but actual availability and provider naming restrictions are checked by Google. Inventory for name collisions and existing resources first. The selected project and bucket names must match exactly in both phases.

Use an approved Cloud Shell identity with appropriate existing rights and Application Default Credentials (ADC), or supply a short-lived active `gcloud` CLI token **only as an environment variable**:

```sh
export GOOGLE_OAUTH_ACCESS_TOKEN="$(gcloud auth print-access-token)"
# Run the approved plan, then unset it; refresh if it expires.
unset GOOGLE_OAUTH_ACCESS_TOKEN
```

`gcloud` CLI login and ADC are distinct; confirm the identity and selected project before planning. `GOOGLE_OAUTH_ACCESS_TOKEN` is read by both this pinned provider and Terraform's GCS backend; do not pass credentials through variables, `-backend-config`, configuration files, outputs or command-line arguments. Tokens expire and are not refreshed automatically. Do not echo them, enable shell tracing, paste them into tickets/logs or upload credential files. Plans, state and `.terraform/` can contain sensitive values even without intentional secrets: restrict workspace access and never commit or publish them. The ignores cover Terraform state, plans, local variable/backend files and generated directories, not authorization.

## Validation and initial read-only plans

In the approved workspace with only sanitized Terraform source, before any apply:

```sh
terraform -chdir=infra/terraform/bootstrap fmt -check
terraform -chdir=infra/terraform/bootstrap init -backend=false
terraform -chdir=infra/terraform/bootstrap validate
terraform -chdir=infra/terraform/bootstrap test
terraform -chdir=infra/terraform/dev fmt -check
terraform -chdir=infra/terraform/dev init -backend=false
terraform -chdir=infra/terraform/dev validate
terraform -chdir=infra/terraform/dev test
terraform -chdir=infra/terraform/bootstrap init
terraform -chdir=infra/terraform/bootstrap plan -input=false
```

The two native test files use a mock provider and plan-only runs to exercise input validation; the dev test overrides service-import targets, so tests do not contact Google APIs or create resources. `init -backend=false` installs providers for validation but does not configure the dev backend. The GCS bucket does not yet exist, so it cannot support the first dev plan. The following Bash example obtains a read-only preview from a **separate, newly created temporary copy** containing only the canonical dev root's sanitized `.tf` files, except `backend.tf`. Use a distinct `TF_DATA_DIR` for the preview:

```sh
umask 077
DEV_PREVIEW="$(mktemp -d)"
cp infra/terraform/dev/{main,services,storage,registry,firestore,queue,identity}.tf "$DEV_PREVIEW/"
cp infra/terraform/dev/.terraform.lock.hcl "$DEV_PREVIEW/"
terraform -chdir="$DEV_PREVIEW" init
terraform -chdir="$DEV_PREVIEW" plan -input=false
```

This is a preview only; never apply it or treat any empty local preview state as the authoritative dev state. Service imports perform reads during planning, not state adoption; applying the plan would write state. Real checks must confirm the expected imports, unchanged existing default network/Compute service account, resource additions, absence of IAM changes or destructive replacements, and cost/retention categories. Review plan output privately; do not publish project-sensitive inventories, secrets or saved plans. A plan alone cannot establish bucket-name availability, future cloud capacity, application permissions, data authorization or actual cost.

## Approval-gated bootstrap and remote backend

The following actions are **not authorized by this ticket**. The owner must review the actual plan, affected resources/IAM, retention/cleanup, budget and permitted spend, then explicitly authorize ticket 14. Stop if the plan contains unexpected import, update, replacement, destruction or enablement. Do not use `-auto-approve`, `-lock=false` or an unreviewed plan.

1. In the original `bootstrap` root, obtain a fresh plan against the exact reviewed inputs. With owner authorization apply the reviewed bootstrap plan. Its initial state is local and must be kept in a restricted, backed-up location; use no secrets as inputs.
2. After verifying the private versioned bucket and controlling who has state-object access, migrate bootstrap state into a **separate** prefix. Add this non-secret, ignored temporary `backend_override.tf` in the bootstrap root:

   ```hcl
   terraform {
     backend "gcs" {}
   }
   ```

   With the same approved token/ADC environment and the chosen bucket name in `TF_VAR_state_bucket_name`, run the migration interactively:

   ```sh
   terraform -chdir=infra/terraform/bootstrap init -migrate-state \
     -backend-config="bucket=$TF_VAR_state_bucket_name" \
     -backend-config='prefix=lifemate/bootstrap'
   ```

   Confirm the requested state copy only after reviewing source and destination. Verify the migrated state and a fresh plan, and securely retain then dispose of local state backups according to the owner's policy. `backend_override.tf` is needed on each checkout that manages bootstrap after migration; recreating the file is safe, but omitting it points Terraform at local state instead. Never commit this operator-specific override or credentials. Do not use `-reconfigure` to migrate existing state: it ignores the old backend configuration rather than copying state.
3. Initialize the canonical `dev` root using the same state bucket and a different prefix:

   ```sh
   terraform -chdir=infra/terraform/dev init \
     -backend-config="bucket=$TF_VAR_state_bucket_name" \
     -backend-config='prefix=lifemate/dev'
   ```

   The bucket must exist first. For a clean first deployment there is no canonical dev local state to migrate. If a legitimate dev state already exists, back it up securely and use `init -migrate-state` after examining both backend configurations; never overwrite an existing remote state. Existing resources must be imported only as part of a reviewed plan. Do not migrate the empty preview state.
4. Generate and review a **fresh** canonical remote-backend dev plan. It may differ from the preview due to state, concurrency, policy or time; obtain approval of that exact plan before apply. Confirm backend locking, state access and no unexpected existing resources or policy changes. Apply only after approval, then re-plan and perform ticket 14's live privacy, region, lifecycle and IAM verification. Retain release backups before any owner-approved cleanup; remove Terraform deletion safeguards only through a separately reviewed destructive plan.

Restricted code, organizer data, model weights, recordings and private traces remain outside public source and must not be uploaded without the separate organizer/team authorization described in the [implementation plan](google-cloud-implementation-plan.md#restricted-source-and-artifact-placement).

## Exercised evidence — 2026-10-30

In authorized Cloud Shell, Terraform `1.13.5` installed the signed Google provider `6.50.0`. Both roots passed `fmt -check`, `init -backend=false -lockfile=readonly` and `validate`; their retained rejection cases passed **8/8**. Two assertion-free positive plan cases were removed after the real plans exercised valid inputs. The generated provider lockfiles are committed; provider caches, state and saved plans are not.

The real bootstrap plan proposed **one state bucket**, with zero changes or deletions. The separate backend-free dev preview proposed **13 additions**: four artifact buckets, one Docker repository, one Firestore database, one Cloud Tasks queue and six service accounts. It also read **18 already-enabled APIs** as no-op imports, with zero changes, replacements or deletions. No IAM grants, default network/default Compute service-account changes, application deployment or compute workload appeared in either plan. Imports have not been adopted into state because no apply occurred.

The imported API plan JSON represents `disable_on_destroy` as `null`, while its configuration expression is explicitly `false`; do not interpret this serialization as a verified post-apply state flag. Ticket 14 must verify the adopted state and a fresh canonical plan before any later lifecycle operation.

The Markdown smoke check resolved **30 local links across README and both cloud runbooks**. The cloud-rendered README was visually inspected in Chromium. These checks do not establish deployed infrastructure, remote-state migration, live IAM/privacy behavior, actual cost, bucket-name availability or GPU capacity. **No persistent-resource/IAM apply, restricted artifact transfer or GPU execution was performed.** Ticket 14 remains owner-approval-blocked.

## References

- [Terraform GCS backend and partial configuration](https://developer.hashicorp.com/terraform/language/backend/gcs); [backend migration](https://developer.hashicorp.com/terraform/cli/commands/init); [Google state bootstrap example](https://cloud.google.com/docs/terraform/resource-management/store-state).
- Pinned Google provider: [bucket](https://github.com/hashicorp/terraform-provider-google/blob/v6.50.0/website/docs/r/storage_bucket.html.markdown), [Artifact Registry](https://github.com/hashicorp/terraform-provider-google/blob/v6.50.0/website/docs/r/artifact_registry_repository.html.markdown), [Firestore](https://github.com/hashicorp/terraform-provider-google/blob/v6.50.0/website/docs/r/firestore_database.html.markdown), [Tasks queue](https://github.com/hashicorp/terraform-provider-google/blob/v6.50.0/website/docs/r/cloud_tasks_queue.html.markdown), [project service](https://github.com/hashicorp/terraform-provider-google/blob/v6.50.0/website/docs/r/google_project_service.html.markdown), [service account](https://github.com/hashicorp/terraform-provider-google/blob/v6.50.0/website/docs/r/google_service_account.html.markdown).
- [Storage lifecycle](https://cloud.google.com/storage/docs/lifecycle), [bucket naming](https://cloud.google.com/storage/docs/buckets#naming), [registry cleanup](https://cloud.google.com/artifact-registry/docs/repositories/cleanup-policy), [Firestore locations](https://cloud.google.com/firestore/docs/locations), [Cloud Tasks retry policy](https://cloud.google.com/tasks/docs/reference/rest/v2/RetryConfig).
