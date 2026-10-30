# Cloud operations

This is source and an operator procedure, not deployment or spending evidence. Follow the [implementation plan](google-cloud-implementation-plan.md), [foundation controls](cloud-foundation.md), [connection guide](cloud-connection.md), and [SDK evidence](sdk-contract.md). No build, cloud mutation, restricted transfer, GPU run, publication, Terraform apply or live smoke is authorized by this document. Scripts do not log in, change the active gcloud project, enable APIs, pull images, or apply infrastructure.

Lazier alternative: use the read-only probes and inventory until a deployment and one bounded synthetic job are separately approved. Do not create real-data GPU work merely to demonstrate the dashboard.

## Selection and approvals

Every script requires:

```sh
export LIFEMATE_PROJECT='<explicit-approved-project-id>' # GOOGLE_CLOUD_PROJECT is the only fallback
export LIFEMATE_REGION=asia-southeast1
export LIFEMATE_TARGET=lifemate
```

`lifemate` selects the reviewed fixed deployment: Cloud Run `lifemate-web`, `lifemate-api`, `lifemate-dispatcher`; Cloud Tasks `lifemate-dispatch`; Scheduler `lifemate-reconcile`. No inferred account/project/region/target and no automatic region failover. Empty project, region or target exits 2 before any external operation; a different region or target is refused. The offline script records cloud selection as provenance but invokes no cloud client.

Keep four distinct owner decisions: (1) foundation/service/IAM/state and retention plan plus permitted spend; (2) private source/build workspace and restricted artifact placement consistent with organizer rules; (3) bounded synthetic or separately approved real GPU execution; (4) verified final package publication/submission. Approval of one is not approval of another. Store approval references in approved private records, not credentials or restricted payloads in this repository. A script approval variable is an operator assertion, not an authorization system.

Before any billable work, verify current paid billing eligibility, remaining eligible credit and original expiry, whole-VM regional price, applicable quotas/capacity and approved ceiling. Free Trial cannot provision GPU VMs. An L4 quota observation is neither capacity nor spending approval. Reserve startup, image/model loading, execution, cleanup, disks, registry, storage/operations, builds, logs, transfer and tax. Budget alerts, task timeouts and the application reservation are not hard billing caps. Start with one on-demand L4, zero application/sample reruns until SDK recovery is approved, no standby GPU.

## Artifact authorization and build boundary

Use an approved private GCP workspace/Cloud Build for all development builds/checks. GitHub is source/review/trigger, not a place to stage private build input or run restricted workloads. A public clone does not contain the private candidate, organizer SDK, models or labels. Before transferring anything, record allowed source/data/model versions, licenses, parameter counts, release dates, destination IAM and retention; owner approval cannot override organizer restrictions.

Never bulk-copy the organizer tree, `<split>_environment/`, serialized ToolEnv/SQLite/pickle state, historical private traces or evaluation labels. Only the official SDK may access environment resources. Keep evaluator-only labels out of policy inputs, model-visible manifests and normal logs. No raw audio/transcripts/tool observations, credentials or model tokens in logs, Terraform values/state, image layers, build args, committed files or public artifacts. Use temporary federation/attached identities, not JSON keys. Sanitized object identifiers/hashes/generations belong in approved private deployment inputs; data bytes do not.

### Build contracts

Build from the repository root. `services/lifemate_api/Dockerfile` serves the human API and the separately launched dispatcher; `apps/web/Dockerfile` serves standalone Next.js. Both images contain sanitized service source only. `workers/gpu_eval/Dockerfile` is the adapter, not a replacement ASR/planner/ToolEnv implementation. Its real CLI requires a run manifest, `--pinned` identities and `--launcher` Python module providing `read_identities`, `fetch`, `read`, `execute`, `commit`. The approved cloud launcher owns generation-aware GCS commits, result publication and the existing real inference path. Mounted data/models are read-only; results use create-only/get GCS APIs, not an overwrite-capable results FUSE mount.

Worker inference dependencies must come from an explicitly approved digest-pinned `WORKER_RUNTIME_IMAGE`; no implied selected model, runtime or weights are supplied in the public source. `submission/Dockerfile` requires a distinct named private payload build context containing executable `launcher`, `app/`, `sdk/`, nonempty `models/`, fully hash-pinned `requirements.lock` and `wheelhouse/`; installation is local-only with no build-step network. Do not substitute a synthetic launcher, fixture, existing completed submission or mounted host model cache for the real implementation. The root `.dockerignore` permits sanitized service source/locks/config only, not private payload, models, baseline, credentials, Git or generated build output.

The submission image's private packaging entrypoint is `/opt/submission/launcher`; that is a team contract, **not an organizer-confirmed launcher**. Required build inputs are `SUBMISSION_RUNTIME_IMAGE=<approved-runtime>@sha256:<digest>`, `PRIVATE_ARTIFACTS_APPROVED=yes`, and named context `approved_submission=/absolute/approved-payload`. Build examples below are gated procedures, not commands exercised by this ticket:

```sh
# Approved private GCP build workspace only. No --push here; publication is separate.
docker build --platform linux/amd64 -f services/lifemate_api/Dockerfile -t lifemate-api:source .
docker build --platform linux/amd64 -f apps/web/Dockerfile -t lifemate-web:source .
docker build --platform linux/amd64 -f workers/gpu_eval/Dockerfile \
  --build-arg "WORKER_RUNTIME_IMAGE=$APPROVED_INFERENCE_RUNTIME" \
  -t lifemate-worker:source .
docker build --platform linux/amd64 -f submission/Dockerfile \
  --build-context "approved_submission=$APPROVED_SUBMISSION_PAYLOAD" \
  --build-arg "SUBMISSION_RUNTIME_IMAGE=$APPROVED_SUBMISSION_RUNTIME" \
  --build-arg PRIVATE_ARTIFACTS_APPROVED=yes \
  -t lifemate-submission:source .
```

Review all input/runtime dependency pins and inventory before building. A local tag is only build staging. Deployment and offline execution require the resulting **full repository `@sha256:` digest**, never a tag. Registry authentication, approved publication and local acquisition of that digest are separate explicit operations; `test_offline.sh` uses `--pull=never`.

## Reviewed deployment

Reuse `infra/terraform/dev/identity.tf` runtime identities: `sa-web`, `sa-api`, `sa-dispatcher`, `sa-batch-worker`, `sa-task-caller`, `sa-scheduler-caller`. Do not replace them, conflate the task caller with the worker, or grant Owner/Editor. Web invokes only API; task/scheduler callers invoke only the machine service. Dispatcher can create/read/cancel Batch and read result manifests under `manifests/` plus objects under the reviewed `RESULT_PREFIX` (`runs/` by default), not input data or result writes. Worker reads approved inputs/models and creates/reads only those same result namespaces; it cannot delete, manage IAM/billing, or create jobs. Result bindings use these two object-prefix conditions, never whole-bucket access. The IAM correction preserves the existing separate manifest-publication contract instead of deriving a manifest from unverified outputs. Keep Google-managed Batch/Tasks/IAP service agents separate.

Production inputs are explicit. Prepare reviewed private values outside the repository for these `infra/terraform/dev` variables:

| Group | Required variables / constraint |
| --- | --- |
| Existing foundation | `project_id`, `region` (`asia-southeast1`), `bucket_prefix`; reviewed backend/state location from the foundation runbook |
| Images | `api_image_digest`, `web_image_digest`, `batch_image_digest`: exact same-project regional `lifemate-images` digests; Batch digest equals catalog image digest |
| Worker | `batch_boot_disk_type` (`pd-balanced` or `pd-ssd`, never `pd-standard`), `batch_boot_disk_gb` (50–1000), explicit `batch_arguments` worker arguments only (the image already has `python -m workers.gpu_eval.main` ENTRYPOINT); `approved_input_prefix`, `approved_model_prefix` |
| API policy | `api_roles` (explicit Google identities/roles including an owner), `api_catalog_json` (approved dataset/model hashes and object generations, experiments with expected output names, benchmark/mode/config, full source SHA, exact worker image, Singapore G2 tier, timeout, zero retries) |
| Safety/results | `dispatcher_budget_cents`, `dispatcher_deadline_seconds` (greater than task timeout), `result_prefix`, scoped child `api_result_prefixes` for redacted metadata only |
| Billing alerts | `billing_account_id`, `budget_amount`, `budget_currency`, `budget_alert_email`; none proves available credit or changes billing linkage |
| CI federation | `github_repository`, numeric `github_repository_id`, numeric `github_owner_id`, `github_branch`, `github_workflow`, `github_environment`; exact protected manual `workflow_dispatch` claims with `ref_protected=true`, not fork PR trust |

Terraform supplies API `GOOGLE_CLOUD_PROJECT`, `LIFEMATE_FIRESTORE_DATABASE`, `LIFEMATE_IAP_AUDIENCE`, `LIFEMATE_ROLES`, `LIFEMATE_CATALOG`, and `LIFEMATE_DISPATCH_URL`, `LIFEMATE_DISPATCH_AUDIENCE`, `LIFEMATE_TASKS_QUEUE`, `LIFEMATE_TASKS_LOCATION`, `LIFEMATE_TASKS_SA`. Dispatcher configuration includes `PROJECT_ID`, `REGION`, `FIRESTORE_DATABASE`, `DISPATCH_URL`, `DISPATCH_AUDIENCE`, `TASKS_LOCATION`, `TASKS_QUEUE`, `TASK_SERVICE_ACCOUNT`, `RESULTS_BUCKET`, `RESULT_PREFIX`, `BUDGET_CENTS`, `DEADLINE_SECONDS`, `BATCH_IMAGE`, `BATCH_SERVICE_ACCOUNT`, machine/disk/time/retry limits, `BATCH_ARGUMENTS` and `BATCH_MOUNTS`. Mount entries are semicolon-separated `bucket remote path [comma-separated-options]`; Terraform mounts only approved data/model prefixes at `/mnt/data` and `/mnt/models`, `ro`. No launcher command default should be treated as runnable production configuration.

1. Review foundation/state migration authorization first; do not initialize/migrate a backend against an inferred project.
2. In the approved GCP workspace, run the existing CPU/service checks and approved build/pin review. Integration owner runs checks once after source integration; none is evidence merely because documented here.
3. Review a fresh Terraform plan with the explicit private variable file. Confirm no replacement/deletion of existing identities, Firestore or artifact buckets; inspect IAM, region, images, Scheduler, budgets, retention and WIF conditions. Save plan and approval privately; Terraform values/state are not secret storage.
4. Only the authorized owner applies that exact reviewed plan. No script here applies. External/personal Google accounts may require owner-operated IAP/OAuth Console setup first. Do not make web public or introduce a second auth system to bypass that prerequisite.
5. Read outputs: `project_id`, `region`, `service_urls`, `service_audiences`, `iap_audience`, `dispatch_queue`, `reconcile_scheduler`, `runtime_service_accounts`, `artifact_buckets`, `image_repository`, `github_wif_provider`, `ci_deploy_service_account`, `ci_build_service_account`, `budget_name`. Match them to selections before probing. CI build identity is registry-scoped; it does not imply Cloud Build submission, private source staging or data-read approval.
6. Verify denial and role-limited actions at the actual IAP web front door before GPU submission. Then run the smallest separately approved synthetic slice. A service being IAM-private means authenticated, not network-internal; do not assume Cloud Tasks/Scheduler/internal ingress routing or add unreviewed NAT/VPC resources.

Apply-time verification still includes approved image existence, pinned GCS generations, current billing/currency and alert delivery, exact WIF numeric claims/environment reviewers, initial external-account IAP OAuth setup, and Batch cancellation permissions/API semantics. Provider lock entries must be checked against signed official releases (including local `h1` platform checksums); a checked-in lock is not proof of an exercised provider installation.

## Smoke: actual routes, actual Batch and results

Read-only prerequisites beyond selection: `LIFEMATE_API_URL`, `LIFEMATE_WEB_URL`, `LIFEMATE_API_ID_TOKEN`, `LIFEMATE_WEB_ID_TOKEN`, `LIFEMATE_IAP_ASSERTION`. Supply short-lived credentials through the approved terminal/session, never command-line literals, files in this repository or `set -x`. API token must target the API audience and use a separately approved invoker identity; the forwarded assertion must be a genuine signed IAP user assertion for the configured web audience, not an email header or fabricated JWT. A manual operator does not automatically have API Invoker merely because they can open web IAP. Web token must be valid for its selected IAP front door. Scripts do not mint credentials or weaken IAM. `gcloud` reads use the already authenticated approved operator identity.

```sh
bash scripts/smoke_cloud.sh
```

The script first describes the named Cloud Run services in the selected project/region and requires exact URL matches. It probes real web `GET /` and API `GET /healthz`, `/api/me`, `/api/models`, `/api/runs`; redirects fail rather than leaking credentials to a login/other origin. Default mode performs no POST and claims only these reads, not a deployed worker or results.

Synthetic submission additionally requires all of:

- `LIFEMATE_SMOKE_SUBMIT=1`, `LIFEMATE_SMOKE_SYNTHETIC=1`, `LIFEMATE_SMOKE_APPROVAL` (record reference).
- `LIFEMATE_SMOKE_EXPERIMENT_ID`, `LIFEMATE_SMOKE_DATASET_ID`, `LIFEMATE_SMOKE_MODEL_ID`: already owner-registered, permitted synthetic entries, not organizer cases or labels.
- `LIFEMATE_SMOKE_IDEMPOTENCY_KEY`: retain the same key when investigating ambiguous acceptance; do not make a fresh billable attempt casually.
- `LIFEMATE_SMOKE_WORKER_IMAGE`: exact approved same-project regional worker digest; checked against the actual Batch runnable image.
- `LIFEMATE_SMOKE_RESULTS_BUCKET`, `LIFEMATE_SMOKE_RESULT_PREFIX` (the reviewed `RESULT_PREFIX`; optional `{run_id}` expansion only when that is the actual provisioning contract), `LIFEMATE_SMOKE_EXPECTED_NAMES_JSON` (JSON array exactly matching the server-approved output object names, not sample IDs).
- Optional `LIFEMATE_SMOKE_TIMEOUT_SECONDS` (1–7200; default 900). Poll timeout does **not** cancel or cap job charges.

```sh
LIFEMATE_SMOKE_SUBMIT=1 LIFEMATE_SMOKE_SYNTHETIC=1 \
  bash scripts/smoke_cloud.sh
```

Authenticated teammates may create an experiment with **`POST /api/experiments`**, an `idempotency-key` header and only `template_id`, `dataset_id`, `model_id`, plus optional `label`. Templates and dataset/model IDs must already be owner-registered in the allowlist. Creation persists a user-owned experiment instance and the user-scoped idempotency record atomically; same key/body returns the instance and a changed body conflicts. It does not author benchmarks, upload artifacts or permit arbitrary runtime/image/URI overrides. The dashboard creates an instance from an approved template before submitting when this capability is advertised by the API.
Run acceptance remains **`POST /api/experiments/{experiment_id}/runs`**, with only `dataset_id`, `model_id`, `decoding` and an `idempotency-key` header; configured template IDs remain accepted for existing callers. Created-instance dataset/model choices are pinned and cannot be changed by the run body. The smoke script uses its pre-registered experiment ID, demands HTTP 202 and a real run ID, replays the same request/key and requires that same ID, then polls `GET /api/runs/{id}`, `GET /api/runs/{id}/failures` and actual regional Batch list/describe. It refuses duplicate jobs, changing UID or an unexpected image.

Firestore transaction callbacks read single documents with `document.get(transaction=transaction)`: `Transaction.get(document)` yields snapshots rather than returning one. The local persistence tests preserve that SDK contract for experiment creation/replay, run acceptance and admission.

Success requires API `SUCCEEDED` **and** actual Batch `SUCCEEDED`, then generation-pinned reads of `gs://<results>/manifests/<run_id>.json` and each `gs://<results>/<RESULT_PREFIX><entry.name>#<generation>`. Manifest identity, unique exact expected coverage, positive generations, optional size and SHA-256 of downloaded object bytes must agree with `entry.checksum`. **GCS crc32c/MD5 are not compared to a SHA-256 field.** Synthetic artifact content is held in memory and never printed or saved. Missing manifest/object, wrong generation/checksum or failed CLI read is nonzero, not invented success.

`LIFEMATE_SMOKE_RECONCILE=1` additionally allows real `POST /internal/reconcile` for this run using explicit `LIFEMATE_DISPATCHER_URL` and `LIFEMATE_MACHINE_ID_TOKEN`; this mutates state/queue/job lifecycle and is never a read-only probe. Without it, polling relies on the deployed Tasks/Scheduler paths, which is the preferred scheduled-repair demonstration. Machine Invoker is service-wide; use only an approved temporary operator capability, never a permanent broad grant.

`LIFEMATE_SMOKE_CANCEL=1` waits until an actual Batch job/UID/image has been observed, explicitly requests `POST /api/runs/{id}/cancel`, then waits for a matching observed terminal Batch outcome. A pre-create API cancellation without an observed job does not prove Batch cancellation; inspect durable intent/slot separately. If the job wins the race and succeeds, the normal result verification still applies. No trap or failed poll silently cancels/deletes resources. On timeout/error, retain printed run ID and inspect/cancel under authorization; the job may still incur charges.

This script proves API submission plus a web route probe, not a browser form submission, denied-user handling or viewer restrictions. Record separate actual browser evidence: approved user submits; non-member denied by IAP; viewer cannot submit/cancel; allowed submitter can read and cancel their own run; conflicting same-key request is 409. Never convert mock/fake tests or a synthetic run into real-data/SDK/recovery/target evidence.

## Reconciliation, cancellation and incidents

Scheduler `lifemate-reconcile` invokes machine `POST /internal/reconcile` every minute in UTC. `/internal/dispatch` is the separate Tasks route; no machine routes belong on the human API. Observe Scheduler status/attempts and Cloud Tasks retries in addition to run state. Firestore durable acceptance and enqueue intent must survive a lost enqueue. Deterministic `(run_id, intentional_job_attempt)` identity, request ID and stored Batch UID must survive ambiguous creation. A request-ID deduplication window is not indefinite permission to recreate a missing job.

The singleton project GPU admission slot stays held across provisioning, active execution and uncertain create/cancel outcomes. Queue concurrency one is not that slot. Reconcile the exact named Batch job/UID/spec plus the complete pinned final manifest before terminal success or verified release. Cancellation intent is not terminal cancellation. A deadline request is not proof a VM stopped. Do not clear a slot, delete an uncertain job, pick a new region or start a new attempt merely because a lease expired.

The dispatcher reads accepted time, whole-run deadline and expected output names from the API repository's persisted run metadata, not from `RunRequest`. Missing deadline metadata without an in-instance acceptance fallback raises rather than silently disabling the deadline. A fresh dispatcher process must still enforce the original accepted run's deadline and exact expected coverage.

The pinned Batch client supports `cancel_job`; it returns a long-running Operation, not a terminal job. The dispatcher requests cancellation and separately re-reads the exact job. Smoke waits for the observed Batch state; it does not claim to await or verify the operation itself. Do not replace cancellation with deletion of the job record.

| Incident | Authorized response |
| --- | --- |
| API accepted but no job | Inspect persisted run/request/enqueue intent and Tasks/Scheduler delivery; reconcile original identity, do not submit a fresh key. |
| Create timeout / missing or changing Batch UID | Stop admission, hold slot/reservation, inspect actual Batch and Compute inventory. Escalate ambiguity; no speculative replay with a new identity. |
| Cancel or whole-run deadline race | Record cancel intent via API, reconcile original Batch identity until terminal, then audit VMs/disks. Never call request acceptance a stopped VM. |
| Batch succeeds but manifest missing/conflicting | Keep run unsuccessful and slot held pending verification. Inspect allowed artifacts/generations and coverage; do not manufacture a manifest or overwrite outputs. |
| Worker OOM / runtime error / capacity issue | Preserve sanitized failure/provenance, verify cleanup and price before a separately approved intentional attempt/tier change. No unbounded retries/failover. |
| Worker dies mid-sample | Preserve start marker and failed attempt. No automatic new ToolEnv session/sample replay: organizer continuation semantics remain unresolved. |
| Leaked credential or restricted log/artifact | Stop further exposure, notify owner, revoke/rotate compromised identity through authorized incident process, preserve minimal private evidence and audit access. Never paste secrets/payloads into issue/PR/chat. |
| Billing freshness unavailable or suspected overrun | Stop new admission, obtain owner billing/credit review, reconcile active resources. Alerts and inventories are not invoices. |

`--resume reuse` can adopt only identity- and byte-verified committed samples; a start marker without its committed output fails closed. An intentionally approved rerun requires `--resume restart --accept-restart --attempt <new>`, retaining the failed attempt. When reuse has complete valid coverage but no final manifest, the worker conditionally commits the same generation-pinned manifest before reporting completion; it never reruns a sample to repair that manifest.

Use redacted structured logs keyed by run/job IDs, not payloads or per-sample Monitoring labels. Cloud Run, Batch, Scheduler, Tasks and Firestore evidence must agree; notification arrival alone is not authoritative. Recovery fault injection and real SDK resume remain separate acceptance gates.

## Read-only cost audit and cleanup

```sh
bash scripts/audit_cost.sh
```

The audit inventories selected-region Batch jobs, all project VMs/disks/snapshots/custom images (including resources outside the selected region), Cloud Run, queue, Scheduler, all-region Artifact Registry repositories/image versions/cleanup policies, all project buckets/lifecycle/retention/soft-delete/versioning and live/noncurrent/soft-deleted object metadata. It reads no object content. Broad project inventory deliberately exposes unlabelled/orphaned spend; it is not permission to operate on unrelated resources. Keep output in the approved private terminal/evidence location because identifiers and metadata can be private. LIST/GET requests can incur normal API/storage operation charges; there is no resource mutation.

Billing linkage is read, never upgraded or enabled. To measure freshness of an **existing** approved export, select `LIFEMATE_BILLING_EXPORT_TABLE=<project>.<dataset>.gcp_billing_export_v1_<id>` (or `gcp_billing_export_resource_v1_<id>`), `LIFEMATE_BILLING_LOCATION` and separately approve `LIFEMATE_BILLING_QUERY_APPROVED=1`. Query is SELECT-only, last 30 days, maximum 1 GB bytes billed; it may cost money. It reports latest usage/export timestamps, observed lag, gross cost, credits and currency, not an asserted current balance. No export, dataset or billing policy is created. Without a selected export or if any read fails, the audit is incomplete/nonzero and identifies billing lag as unverified. Owner must inspect current Billing Reports, credit eligibility/expiry, late adjustments, taxes and report freshness. Usage/export lag means neither empty inventory nor reported zero is proof of no charges. See [billing export timing](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables) and [report limitations](https://docs.cloud.google.com/billing/docs/how-to/reports).

Cleanup is **inventory and reconciliation**, never hidden deletion. Compare Batch terminal records with actual VMs, disk `users`, snapshots, images/tags, live/noncurrent/soft-deleted storage bytes and retention/cleanup policies. Detached disk is a review candidate, not permission to delete; terminal Batch record is not proof of VM cleanup. Retained object versions, soft deletion, registry layers, logs and Terraform state can continue to cost money.

Teardown requires a separate owner-approved resource-by-resource plan:

1. Stop new admission and approved build/deploy triggers; drain/cancel runs through the real lifecycle and retain immutable run/job/UID evidence.
2. Reconcile Batch terminal state and Compute VM/disk cleanup. Pause queue/Scheduler only as an approved mutation and only after deciding how pending intents will be resolved; pausing either does not stop an active Batch VM.
3. Preserve verified release image, checksums, manifest, licenses and authorized backup externally before credit expiry. Do not publish development artifacts or organizer material.
4. Review removal of service/IAP/WIF/temporary operator permissions and image/object retention against incident/release needs. Foundation bucket protection, retention/soft deletion and Cloud Run deletion protection are deliberate barriers; do not bypass with force-delete or broad `terraform destroy`.
5. The owner reviews a fresh exact-target deletion plan and applies only authorized changes. Never delete shared foundation/state/labels to hide spend. Run the read-only audit again after the authorized cleanup and later after billing lag; record remaining resources, retained bytes and unsettled charges.

## Offline execution and unresolved launcher details

Portal-confirmed: private mount shape like public test at `/data`; output is `result/submission.jsonl`; fully offline; one A30, 16-core Xeon Gold 6442Y, 64 GB RAM; each sample within 30 seconds. **Unconfirmed:** official executable/entrypoint and arguments, allowed base/CUDA image, absolute working/output directory and mount mapping, SDK provisioning/private layout, model packaging details, exact timing boundary and compliant mid-sample continuation. `/opt/submission/launcher` and any operator-selected output mount below are private rehearsal conventions only, never official guidance.

Prerequisites: approved private workspace/fixture and existing exact-digest image, approved GPU execution, NVIDIA Docker runtime, all runtime weights/SDK/dependencies embedded in the image, and a reviewed real private launcher. `LIFEMATE_OFFLINE_EXPECTED_IDS` is a UTF-8 JSON file containing a unique nonempty ID array derived only from permitted input rows; the script never enumerates environment files. Output directory must exist and be empty, separate from input. No download, install, auth, cache mount or telemetry at runtime.

```sh
export LIFEMATE_OFFLINE_IMAGE='<repository/image>@sha256:<real-approved-digest>'
export LIFEMATE_OFFLINE_DATA='<absolute-approved-public-test-shaped-fixture>'
export LIFEMATE_OFFLINE_OUTPUT='<absolute-existing-empty-output-directory>'
export LIFEMATE_OFFLINE_OUTPUT_MOUNT='<explicit-private-launcher-absolute-output-directory>'
export LIFEMATE_OFFLINE_EXPECTED_IDS='<absolute-approved-id-array.json>'
export LIFEMATE_OFFLINE_APPROVAL='<private-approval-record-reference>'
LIFEMATE_OFFLINE_RUN=1 bash scripts/test_offline.sh -- <approved-private-launcher-arguments>
```

Arguments after `--` go to the image's embedded `/opt/submission/launcher`; they cannot add Docker mounts/network flags. Zero launcher arguments are supported by ending at `--` if that is the actual approved private launcher. The exact digest is inspected locally and run with **`--pull=never --network none --gpus all`**, read-only root, temporary `/tmp`, read-only input bind at `/data` and the only writable host bind at the explicit output mount. No host model cache, credential, home or Docker socket mount, no forwarded cloud tokens. Image-declared volumes and an entrypoint that differs from the reviewed private packaging contract are refused. Digest identity does not itself prove the image lacks embedded credentials; the private build audit must do that.

The script requires actual container exit success and a new regular `submission.jsonl` in the selected output directory, verifies UTF-8 JSONL, exactly `id/tool_calls/state_hash`, field types/hash shape and exact unique expected ID coverage, and reports SHA-256 without printing payloads. This is structural validation, **not** official scoring, tool-schema validation, same-session executed/rejected-call/hash evidence, 30-second compliance or deterministic replay proof. Obtain the authoritative launcher mapping before official release. Exercise the real audio-to-ASR/planner/one-ToolEnv path, approved same-session integrity validation and repeated clean runs on the required A30; L4/proxy-GPU/synthetic evidence cannot replace those gates. No executable official task scorer has been established in the supplied evidence.

## Refusal checks and evidence status

Integration-owner checks to run without credentials or cloud work:

```sh
env -u LIFEMATE_PROJECT -u GOOGLE_CLOUD_PROJECT -u LIFEMATE_REGION -u LIFEMATE_TARGET bash scripts/smoke_cloud.sh
env -u LIFEMATE_PROJECT -u GOOGLE_CLOUD_PROJECT -u LIFEMATE_REGION -u LIFEMATE_TARGET bash scripts/test_offline.sh
env -u LIFEMATE_PROJECT -u GOOGLE_CLOUD_PROJECT -u LIFEMATE_REGION -u LIFEMATE_TARGET bash scripts/audit_cost.sh
```

Expected (not exercised in this source-writing slice): exit 2 and respectively `smoke_cloud: refusing: set LIFEMATE_PROJECT (or GOOGLE_CLOUD_PROJECT) explicitly`, `test_offline: refusing: set LIFEMATE_PROJECT (or GOOGLE_CLOUD_PROJECT) explicitly`, `audit_cost: refusing: set LIFEMATE_PROJECT (or GOOGLE_CLOUD_PROJECT) explicitly`. Missing region or target after project selection similarly refuses with the variable name. No live smoke, Terraform, container, A30 or billing check is claimed here.

### Known live-deployment blockers

The prior missing Batch task/allocation specification and non-durable dispatcher stores were addressed in this ticket's source integration; those old findings are not live deployment evidence either way. The dispatcher now supplies real Tasks/Batch/durable-store source, but only a permitted live smoke can establish API compatibility, actual GPU provisioning, task timeout/identity/mount correctness, transactional restart/concurrency behavior, Scheduler repair, cancellation and pinned artifact completion. The production launcher/provisioning/commit bridge must be selected and approved explicitly before claiming a runnable real-data worker. The public adapter is not that bridge.

Until the actual private launcher publishes `manifests/<run_id>.json` plus all server-approved relative output entries at the exact reviewed result prefix and generations, smoke cannot prove success. Dispatcher result verification now computes SHA-256 of generation-pinned bytes, verified against local fakes by the integration owner; live GCS comparison is apply-gated, not exercised deployment evidence. Owner IAP/OAuth setup, current spend/data approvals, actual deployed resource evidence, SDK recovery semantics, official offline launcher and A30 qualification also remain explicit gates.
