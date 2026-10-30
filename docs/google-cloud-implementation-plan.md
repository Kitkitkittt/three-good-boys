# LifeMate: integrated Google Cloud implementation plan

Planning review: 2026-10-30; updated after the connection and Terraform-plan work recorded in tickets 12–14. This combines the README assessment, the parent `LifeMate_Google_Cloud_Implementation_Handoff_2026-10-30.md`, existing tickets and official documentation. Observations are dated snapshots, not evidence of deployment or authorization to spend.

## Decision

Use Google Cloud for the shared experiment dashboard, orchestration, GPU development and private artifacts. Preserve the existing Python inference/evaluation code. Export the selected implementation as a separate, fully offline competition image.

Keep the requested Next.js + FastAPI stack, but start with one human-facing web deployment, one private API deployment, and one separate machine-only dispatcher/reconciler deployment. Reuse the API container image for the machine deployment where practical. Use Cloud Tasks, Cloud Scheduler, Firestore, GCS, Artifact Registry and one on-demand Batch/G2 L4 worker. Do not create a second inference implementation or the handoff's full package/module tree.

Lazier alternative: a small server-rendered FastAPI dashboard removes Next.js and its service hop. Retain Next.js here because it is the proposed stack; reconsider only if the owner prioritizes fewer moving parts over that UI stack.

## 1. Evidence and corrections

| Area | Observed evidence | Consequence |
| --- | --- | --- |
| Public front door | Canonical public `huyxdang/three-good-boys` main README contains only `# three-good-boys`; authenticated repository permission is READ | README feedback is accurate. Changes need owner review/merge; do not assume upstream deployment rights. |
| Local overview | The integration-branch README now explains the problem, candidate pipeline, dated evidence and authorized setup; its pipeline is a numbered description rather than the proposed diagram | Ticket 12 is done. A diagram remains an optional presentation improvement; do not imply the public `main` README has already changed. |
| Runtime | Shared baseline remains Mac/MLX; a separate private CUDA candidate, pinned Linux requirements, paired diagnostic and local checkpoints have recorded proxy-GPU runs, but ticket 03 is still blocked | Integrate and qualify that candidate before real cloud inference; do not assume the shared baseline is a runnable GPU worker or rebuild ASR, planner, ToolEnv or scoring. |
| Quality | Recorded paired runs on 12 frozen training cases yielded approximate local 8.33/100 in both modes; no-action diagnostic yielded 16.67/100 due to two empty-gold cases | This is diagnostic evidence, not an official score or representative accuracy estimate. Publish aggregates only with team approval. |
| Performance | Recorded proxy-GPU sample timing included 3/12 over 30 seconds; p95/max 37.86 seconds | Quality and latency are unfinished. L4 does not certify A30. |
| Packaging | Prior network-disabled CUDA candidate used mounted weights on proxy hardware | Final image still needs embedded assets and target-hardware proof. |
| Cloud state | The selected project was observed active with billing enabled, the linked billing account open, required APIs enabled, and unused global and Singapore L4 quota of one each | These are dated observations, not proof of current credit, capacity, authorization or a deployed platform. See [cloud connection](cloud-connection.md). |
| Foundation and tooling | The CLI was available by absolute path; Terraform was subsequently used in authorized Cloud Shell. Ticket 13 records validated configuration and real read-only plans; ticket 14 remains blocked | Apply and remote-state migration require fresh reviewed plans and explicit owner approval. No persistent foundation/IAM apply or GPU workload is claimed. |

Source pointers: [training evaluation](training-evaluation.md), [SDK contract](sdk-contract.md), [working baseline](working-baseline.md), [ticket index](../.scratch/lifemate/README.md), [public README](https://github.com/huyxdang/three-good-boys/blob/main/README.md).

### Current organizer contract

The live [LifeMate portal](https://challenge.zalo.ai/portal/lifemate), including Rule, Evaluation and Submission Guidance, was rendered and read during this review:

- Fewer than 6B total model parameters; LLM fewer than 5B; context at most 16,384 tokens. Quantization does not reduce parameter count.
- Open-source models/public resources must be released before 26 October 2026 and have suitable licenses. No public/private-test labeling for training or tuning.
- Fully offline inference; one NVIDIA A30, 16-core Intel Xeon Gold 6442Y and 64 GB RAM; each sample within 30 seconds.
- Exactly one ToolEnv per sample; all calls appear in submission. No agent reading, copying or parsing files under `<split>_environment/`.
- Private mount has public-test structure at `/data`; output is `result/submission.jsonl`.
- Complete solution includes training code, inference code and data in a Docker package, checksum and public Google Drive download link. Solution submission: 16 November, 23:59 GMT+7; at most two submissions, last evaluated.
- Private release: 20 November, 09:00; frozen-solution results due 23 November, 23:59 GMT+7.

Still unresolved: exact launcher/base-image restrictions, detailed inference timing boundary, permitted checkpoint/session continuation and approved cloud placement of organizer material. Resolve these through current organizer guidance; do not invent an official executable scorer. The local evaluator remains an approximation.

### Changes required to the cloud handoff

1. Free Trial cannot provision GPU VMs. Paid upgrade needs explicit owner authorization; remaining eligible welcome credit keeps its original expiry. Budget alerts are not a hard cap on Batch/Compute charges. [Free Trial](https://docs.cloud.google.com/free/docs/free-cloud-features), [budget behavior](https://docs.cloud.google.com/billing/docs/how-to/budgets).
2. Singapore supports Batch/G2 and listed L4 zones, but availability listings are not quota/capacity guarantees. G2 needs the documented L4/global GPU quotas, not a separate ordinary CPU quota; verify disk and other selected quotas too. [GPU quota](https://docs.cloud.google.com/compute/resource-usage#gpu_quota), [locations](https://docs.cloud.google.com/compute/docs/regions-zones/gpu-regions-zones).
3. Cloud Tasks throttles HTTP dispatch, not GPU execution. A Firestore admission slot must remain held until Batch reaches a verified terminal outcome.
4. Add Cloud Scheduler reconciliation. Firestore and Cloud Tasks cannot commit atomically; Pub/Sub events are optional hints, not the source of truth.
5. GCS object uploads are atomic individually. Use conditional create, object generations and a final checksum manifest, not filesystem-style atomic rename assumptions. [GCS preconditions](https://docs.cloud.google.com/storage/docs/request-preconditions).
6. The existing candidate pickles whole ToolEnv episodes. There is no documented SDK session restore interface. Do not upload SQLite/pickle checkpoints or claim arbitrary mid-sample recovery is compliant.
7. Cloud Run Invoker IAM is service-wide. Separate privileged machine routes from the human API; distinguish user identity, service invocation identity and CI federation identity.
8. Keep the existing measure → model selection → grounding → residual post-training decision order. Platform work must not skip or replace quality gates.

## 2. Deployment and data seams

| Module | Deployment/interface | Responsibility |
| --- | --- | --- |
| Web | Next.js, Cloud Run, direct IAP | Google login, submit/compare runs, view redacted failures and artifact metadata |
| API | FastAPI, IAM-private Cloud Run | Verify forwarded signed user assertion, authorize roles, validate immutable run requests, persist enqueue intent |
| Dispatcher/reconciler | Separate IAM-private Cloud Run | Cloud Tasks dispatch, Scheduler reconciliation, admission/budget slot, Batch lifecycle and cancellation |
| GPU worker | One foreground Python task, Batch G2/L4 | Verify approved artifacts, reuse runner/evaluator, commit permitted results and integrity manifest |
| Offline runner | Existing Python core, submission image | Local-only models/SDK/input, genuine calls and hash, no GCP SDK/auth/telemetry requirement |

Flow: teammate uses the web; web invokes API with a Google service ID token and forwards the signed IAP assertion; API persists run/intent and schedules short dispatch; dispatcher starts Batch; worker writes private artifacts; reconciler verifies Batch plus artifact completion; web polls the API.

Default human auth: direct Cloud Run IAP with approved Google identities and app roles. Verify assertion signature, issuer, frontend audience and expiry at the API; never trust an unsigned email header. Personal/external accounts may need a custom OAuth client and initial owner-operated Console setup. If that setup prevents IAP use, select Firebase Google sign-in plus verified backend tokens as an explicit alternative, not a second parallel auth system. [IAP](https://docs.cloud.google.com/run/docs/securing/identity-aware-proxy-cloud-run), [signed assertions](https://docs.cloud.google.com/iap/docs/signed-headers-howto).

IAM-private means authenticated, not automatically network-internal. Configure Cloud Tasks/Scheduler ingress deliberately. Do not add a VPC/NAT just to label a service private; Cloud Run-to-Cloud Run internal-only ingress has additional routing requirements. [Ingress](https://docs.cloud.google.com/run/docs/securing/ingress).

### Restricted source and artifact placement

- Existing public repository remains a sanitized presentation/control-plane surface unless the owner approves a different visibility/source arrangement. Ignored baseline/data files do not become available through a public clone.
- Establish an authorized private GCP source/build workspace and private Artifact Registry before building restricted worker/submission images. All planned development checks and builds execute in approved GCP workspaces/Cloud Build; GitHub remains the source/review and trigger surface, not a dependency on GitHub-hosted compute. No public runner downloads competition data or emits private logs/artifacts. GitHub Actions may submit reviewed GCP builds via WIF; retain a GCP-native trigger if all CI execution must remain on GCP. Restricted source/artifact transfer still waits for its separate authorization.
- Separate approved datasets/audio/models from policy inputs and evaluation labels. The agent receives only permitted request/context/history/tool schemas and observations from official ToolEnv calls; evaluator-only labels never enter prompts or model-visible manifests.
- No bulk upload of the existing organizer tree, environment directories, serialized ToolEnv state or historical private traces. Cloud execution needs an organizer-approved provisioning mechanism by which the official SDK can access its required resources without forbidden agent file access. Owner approval alone cannot override challenge rules.
- GCS buckets use public-access prevention, uniform access, scoped identities, lifecycle rules and same-region placement. Raw audio/transcripts/tool results stay out of normal logs and traces. Approved redacted failure artifacts require API authorization.
- Final organizer-requested public Drive publication is a separate explicit owner action for the verified release, not permission to publish development artifacts on GitHub.

## 3. Small repository footprint

The README and reviewed Terraform bootstrap/dev roots already exist. Application, worker, deployment and smoke-test paths below are proposals, not claims of implemented services.

| Path | Change |
| --- | --- |
| `README.md` | Existing public-facing problem, example, candidate pipeline, dated status and setup paths; optionally replace the numbered pipeline with a current-state diagram, not an aspirational deployment diagram |
| `docs/working-baseline.md`, `docs/sdk-contract.md`, `docs/training-evaluation.md` | Correct stale status and add exercised cloud/target evidence; keep decision order in its existing document |
| `apps/web/` | Next.js dashboard and trusted API hop; no model execution or GCP credentials in browser |
| `services/api/` | API, request models and shared Firestore helpers |
| `services/dispatcher/` | Dispatch and scheduled reconciliation; reuse shared request/state code rather than a generic framework |
| `workers/gpu_eval/main.py` | Manifest adapter over current inference/evaluation functions |
| `workers/gpu_eval/checkpoint.py` | Conditional completed-result commit and provenance verification, only after compliance decision |
| Existing private `baseline/` | Selected CUDA candidate, portable split entrypoint and completed-sample validation; retain paired diagnostic as a distinct mode |
| `docker/Dockerfile.api`, `docker/Dockerfile.web`, `docker/Dockerfile.worker`, `docker/Dockerfile.submission` | Pinned builds with explicitly different cloud/offline dependencies and asset inventories |
| `infra/terraform/bootstrap/` | Existing reviewed state-bucket configuration; apply and remote-state migration remain owner-gated |
| `infra/terraform/dev/` | Existing reviewed identity, storage, registry, Firestore, queue and API configuration; add actual service, scheduler, observability and billing resources only with their reviewed implementations |
| `.github/workflows/ci.yml` | Unprivileged CPU/control-plane checks and Terraform validation |
| `.github/workflows/build-worker.yml` | Protected manual trigger for approved private worker build; no restricted artifacts on public runners |
| `.github/workflows/deploy-cloud.yml` | Reviewed plan/apply/deploy via scoped OIDC, immutable digests |
| `.github/workflows/release-submission.yml` | Protected manual release orchestration in approved private build environment |
| `scripts/smoke_cloud.sh`, `scripts/test_offline.sh`, `scripts/audit_cost.sh` | Runnable acceptance checks; operate only against explicitly selected resources |
| `docs/cloud-operations.md` | Deployment, artifact authorization, reconciliation, cancellation, incident handling and teardown; one runbook rather than five overlapping docs |

Before selecting code, reconcile the preserved candidate under `work/ticket-03-port-20261028/candidate-files/`, the portable-root experiment and paired diagnostic. Do not replace the original bundle or pretend those experiments are already one production implementation.

## 4. Minimum API and job contracts

Endpoints: `GET /healthz`, `GET /api/me`, `GET /api/models`, `POST /api/experiments`, `POST /api/experiments/{id}/runs`, `GET /api/runs/{id}`, `GET /api/runs/{id}/failures`, `POST /api/runs/{id}/cancel`; machine-only `POST /internal/dispatch` and `POST /internal/reconcile`.

Start with owner-registered dataset/model manifests, not browser upload infrastructure. Add upload endpoints only when team use requires them. No arbitrary image, shell command, GCS URI, machine tier or worker configuration from the browser.

Experiment creation instantiates an owner-approved catalog template; it does not author a new benchmark or accept arbitrary runtime policy. `POST /api/experiments` accepts only `template_id`, approved `dataset_id`/`model_id` and optional `label`, with a user-scoped idempotency key, and atomically persists an experiment instance plus its idempotency record. The dashboard uses this advertised creation capability before submitting runs; configured template IDs remain valid for existing callers.

Run submission uses a user-scoped idempotency key. The server resolves approved dataset/model IDs to hashes and pinned object generations, records source SHA and approved image digest, mode, decoding configuration, benchmark identity, selected machine/region, timeout and retry allowance. Same key/same canonical request returns the existing run; same key/different request returns conflict.

Run metadata includes the approved benchmark identity, dataset/model IDs, mode and a digest of the immutable execution configuration, never raw inputs or decoding payloads. The dashboard compares those identities rather than owner/status. Run-detail artifacts expose only verified object metadata (name, pinned generation, checksum and size); content/download, scoring and latency fields are not inferred when the API does not provide them.

Firestore collections: `team_members`, `datasets`, `models`, `experiments`, `runs`, plus one admission-slot document and per-run audit events/idempotency records. App roles: owner controls approvals/cost policy; maintainer manages approved artifacts; researcher submits permitted experiments; viewer reads approved metadata.

### Durable lifecycle

- Run states: `QUEUED`, `SUBMITTING`, `ACTIVE`, `SUCCEEDED`, `FAILED`, `CANCELED`. Store observed Batch phase separately; cancellation intent is not terminal cancellation.
- Accept transaction atomically stores request identity, run and enqueue intent. Return `202` for durable acceptance; enqueue outside the transaction. Reconciler repairs lost enqueue operations.
- Admit transaction checks role-approved request, budget reservation and singleton slot, then persists create intent and immutable Batch identity. Do not perform network calls in a Firestore transaction callback.
- Batch identity is deterministic per `(run_id, intentional_job_attempt)`, with stable `requestId` and project/region. Persist returned Batch UID and verify spec on collisions. Retry ambiguous creates with the same identity; no region/attempt switch merely because a lease expired. Batch guarantees request-ID deduplication for at least 60 minutes, not indefinitely: preserve and reconcile the named job and its UID rather than relying on that window or deleting an uncertain job.
- Cloud Tasks retry replays dispatch. Batch task retry stays inside its original job. A separately admitted job is a distinct explicit attempt, not automatic replay after every failure.
- Task queue concurrency of one is insufficient: hold the project-wide GPU slot across provisioning, execution and uncertain create/cancel outcomes. Release only after reconciled terminal resolution.
- Mark `SUCCEEDED` only after Batch success, complete permitted predictions, same-session call/hash integrity evidence, evaluator/provenance validation and a valid final manifest. Counted checkpoint rows or exit code alone are insufficient.
- Scheduler scans queued/submitting/active runs, repairs dispatch, checks actual Batch status and whole-run deadlines, and finalizes artifacts. Pub/Sub can later wake this same path; it never replaces it.
- Cancellation records intent, requests cancellation against the matching job and reconciles the real outcome. Stale/missing/ambiguous jobs hold admission and alert rather than risk duplicate charges.

References: [Cloud Tasks](https://docs.cloud.google.com/tasks/docs/dual-overview), [Batch create identity](https://docs.cloud.google.com/batch/docs/reference/rest/v1/projects.locations.jobs/create), [task retry policy](https://docs.cloud.google.com/batch/docs/automate-task-retries), [Scheduler](https://docs.cloud.google.com/scheduler/docs/overview).

### Worker and checkpoint contract

Reuse model loading and inference, not the current fixed filesystem paths. Accept the official mounted split shape, derive IDs/catalogs from permitted inputs, and keep reference-transcript diagnostics separate from production audio inference. Stage ASR/planner loading as needed for VRAM; explicit warmup must not consume benchmark cases or create ToolEnv sessions. Record cold load, ASR, planning/tool execution and total timing separately.

Commit completed sample output only after checking calls, final hash and successful stop reason against its live session. Include run/config/input identity and checksum; final manifest pins each GCS object generation. Use conditional create (`ifGenerationMatch=0`); reuse an existing object only after verifying identical identity/content. Conflicting outputs fail rather than overwrite. Final export verifies complete unique coverage without reconstructing completed sessions.

**Recovery prerequisite:** the SDK has no documented session restore API, while the existing SQLite checkpoint stores pickled environments. Result-only checkpoints cannot restore an interrupted ToolEnv. Obtain organizer approval/clarification before promising hard-preemption continuation. Until resolved, no automatic retry of a sample that may already have started: persist a start marker, preserve failed attempts and fail closed on ambiguous execution. Graceful stop can complete the current sample before exiting. Do not count a sample-boundary resume demonstration as proof of arbitrary mid-sample recovery.

Cloud orchestration kill-and-reconcile can be proven with permitted synthetic inputs independently. Real-data mid-sample kill-and-resume remains a named acceptance gate; if no compliant continuation mechanism exists, record that incompatibility and obtain an explicit requirement decision rather than ship a false guarantee or silently weaken the gate. Default on-demand execution and zero application-level reruns until recovery is approved; only safe transient setup failures may receive reviewed retries.

## 5. IAM and deployment controls

Bindings below are the starting review set, not permission to grant them. Use resource-scoped/custom roles where supported; Firestore authorization remains in the backend because server credentials bypass client rules.

| Identity | Required capabilities / initial role candidates |
| --- | --- |
| `sa-web` | `roles/run.invoker` on API only; no storage, Batch or billing access |
| `sa-api` | `roles/datastore.user` in application project/database; `roles/cloudtasks.enqueuer` on dispatch queue; `iam.serviceAccounts.actAs` on `sa-task-caller`; narrowly scoped `storage.objects.get` for approved user-visible result metadata, never direct input/label access |
| `sa-task-caller`, `sa-scheduler-caller` | `roles/run.invoker` on machine service only; no user API access |
| `sa-dispatcher` | Batch create/get/cancel/status, scoped Firestore metadata, dispatch-queue enqueue/repair, and `storage.objects.get` on approved result manifests/outputs for generation-pinned verification; no input-data or result write/delete access. Start from `roles/batch.jobsEditor` only if custom minimal permissions are insufficient; `roles/iam.serviceAccountUser` only on worker SA and `sa-task-caller` for authenticated task repair |
| `sa-batch-worker` | `roles/batch.agentReporter`, logging writer, Artifact Registry reader; object viewer on approved input/model buckets, object creator and required read verification on results; no delete, IAM, billing or job-creation rights |
| `sa-ci-build` | Approved registry writer and scoped private build submission/artifact access; no user data access unless explicitly approved for that build |
| `sa-ci-deploy` | Scoped Cloud Run deployment, image read and act-as on runtime SAs; no Owner/Editor or billing upgrade rights |
| Owner/bootstrap identity | Reviewed project/API/IAM/billing/IAP setup and Terraform apply; not a standing application identity |

Keep Google-managed Batch/Tasks/IAP service agents distinct from runtime identities. Validate exact API/service-agent grants against the selected topology before apply. [Batch permissions](https://docs.cloud.google.com/batch/docs/get-started), [Cloud Run deployment](https://docs.cloud.google.com/run/docs/deploying).

GitHub WIF trusts the approved execution repository's actual numeric repository/owner IDs, branch, workflow, event and protected deployment environment. Scope impersonation to a named deployer SA. No static JSON keys, no privileged execution of fork PR content, and no assumption that the existing public fork/upstream has those protections. Pin actions and exclude generated credential files from all images/artifacts. Owner bootstrap IAM is separate from routine application deploy. [WIF](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines).

## 6. Implementation frontier and acceptance

These are proposed implementation slices, not completion claims. Continue using the existing local ticket tracker and the offline #1 / cloud #3 umbrella specs; do not create a competing status board. Once shared contracts are fixed, prepare worker, web/API and dispatcher code in parallel with ticket 14's approval and foundation work. Ticket 14 is a prerequisite for deploying services onto that foundation, not for writing their code or preparing ticket 03 qualification. Use one integration owner for shared inference changes.

Linux/NVIDIA prerequisite: slice C must integrate the private CUDA candidate into the approved worker source, verify pinned dependencies and complete a real audio-to-ToolEnv/export smoke on the approved GCP GPU runtime. Before slice G or model-selection Batch evaluations, ticket 03's acceptance gates must be satisfied or explicitly revised through the existing tracker. Slice E may exercise synthetic orchestration first; that does not prove model execution. Recorded proxy-GPU runs are reuse evidence, not completion of this gate.

Qualification needed to complete tickets 02/03 may run before slice G once its own data, GPU and safety approvals are in place; it does not claim the dashboard or the full platform baseline is complete. This avoids making completion of 02/03 depend on slice G while G itself waits for those tickets. Do not bypass their acceptance criteria or begin grounding before model selection.

| Slice | Depends on | Deliverable and observable acceptance |
| --- | --- | --- |
| A. Front door and decisions | Existing evidence | Ticket 12 delivered the README overview and connection guide. Keep the pipeline and evidence current; a diagram is optional. Confirm private source/data, billing and auth decisions. |
| B. Cloud foundation | A; owner approval for cloud mutations | Ticket 13 delivered reviewed bootstrap/dev Terraform and read-only plans. Ticket 14 requires explicit approval of fresh plans, retention and spend before state migration and apply. Separately review IAM, IAP, Scheduler, observability and budget resources when their real services are ready; verify authorized access and denial. |
| C. Portable worker/offline core | Existing 02/03 work and shared contracts for code; data/SDK and GPU approvals for real execution | Prepare candidate integration, dynamic input handling, artifact manifests, pinned builds and ticket 03 qualification alongside B/D/E, without transferring restricted material. After approval, run a permitted fixture through the actual SDK and export in an approved GCP GPU workspace; offline inference has no GCP dependency. |
| D. Team dashboard and API | Fixed contracts with C/E for code; B and reviewed deployment/IAM for deployment | Implement in parallel with B/C/E. After deployment, exercise experiment creation, durable run acceptance, status and redacted results on the actual surface, including denied users, role limits and idempotency conflicts. No GPU needed. |
| E. Dispatch/reconciliation | API/run contract for code; B, reviewed deployment/IAM and workload approval for execution | Implement in parallel with B/C/D. After deployment and approval, run a synthetic web-submitted Batch job and verify deterministic identity, singleton GPU slot, budget reservation, Scheduler repair, cancel/deadline logic and duplicate handling. |
| F. Recovery qualification | C/E; approved session semantics | Failure injection around enqueue/create/commit/cancel; graceful completed-boundary recovery; approved hard-interruption behavior exercised or explicitly blocked. Missing/conflicting outputs never appear successful. |
| G. Real cloud baseline | C's Linux/NVIDIA runtime gate; existing 02/03 acceptance gates satisfied or explicitly revised; D/E/F required safety gates; approved artifacts and GPU allocation | Fixed existing 12-case diagnostic (not a new convenient 10-case comparison) runs in both reference/ASR modes; manifests, score limitations, ASR/critical slots, per-case outcomes, timing/VRAM and billed-resource report visible in dashboard. Scale to a predeclared larger training evaluation set before generalizing. |
| H. Measured model/grounding work | G plus existing 02/03 gates | Existing 05 compares compliant candidates; existing 04 then changes constrained decoding/prompt/lookup/order/clarification one change per frozen run. Keep only measured improvement without unexplained regression. Dashboard compares identical benchmark/config identities. |
| I. Release and target proof | H plus existing 07/08/09 | Exact image includes weights/tokenizers/SDK/assets; actual offline evaluator/runner integration, A30 latency/memory, deterministic repeated outputs, licenses/count/context and final package manifest checked. No cloud credentials/network required. |
| J. Owner submission/private run | I, then organizer release | Existing 10 handles verified Drive/checksum/portal acceptance; existing 11 runs only frozen solution on private release and submits before official cutoff. Keep release backup and tear down development resources. |

Repair the existing ticket-03 private-data dependency explicitly: verify a permitted public-test-shaped `/data` fixture and dynamic catalog/IDs before release, and reserve actual private-release verification for ticket 11. Do not mark 03 complete from that edit; profile/history behavior and same-input Mac comparison requirements remain unresolved unless separately satisfied or explicitly revised. Existing 04 depends on 02 and 05; existing 07/08/09 remain release gates.

Cloud slices map to local tickets 15–23: 15 shared contracts; 16 private API; 17 dispatch/reconciliation; 18 dashboard; 19 worker adapter; 20 containers, service Terraform and operations source; 21 approved deployment with a synthetic slice; 22 failure injection and recovery; 23 the real 12-case cloud baseline. Slices C/D/E/F/G remain the acceptance view; the tickets carry ownership and progress.

### Measurement and post-training gate

Follow [decision-order.md](decision-order.md), not an independent cloud-model roadmap: frozen real baseline; same-case ASR/model comparison; schema/grammar-constrained decoding and measured grounding; documented plateau; only then category-specific LoRA if held-out improvement exceeds observed variance with no regression. ASR LoRA only if measured critical-slot failures dominate. Keep training labels/benchmark firewall and context budget intact. Parameter eligibility, license and release date are checked for every selected model/revision.

Fine-tuning is conditional work, not mandatory platform infrastructure. If it becomes justified, use the same bounded Batch worker/artifact contract with a separate approved training configuration; do not add a general training platform first.

### Verification commands/scenarios to implement

All following development checks/builds are planned for the approved GCP workspace, Cloud Build or Batch. Network-disabled container verification can run there too; A30 qualification remains a separate mandatory matching-hardware gate. Previously exercised foundation validation and read-only plans are recorded in [cloud-foundation.md](cloud-foundation.md#exercised-evidence--2026-10-30); they are not deployment evidence.

- CPU/control plane: repository's existing Python checks plus deterministic behavioral checks for idempotency conflict, state transitions, authorization and immutable-result conflicts. No source-text or mock-echo tests.
- Terraform: `terraform -chdir=infra/terraform/dev fmt -check`, `terraform -chdir=infra/terraform/dev init -backend=false`, `terraform -chdir=infra/terraform/dev validate`; authorized backend plan is a separate protected operation. No PR auto-apply.
- Cloud: `scripts/smoke_cloud.sh` submits through the real web/API, observes one actual Batch job and verifies generation-pinned results; browser proof includes denied-user and role-limited actions. Run synthetic fixtures before approved real data.
- Fault injection: duplicate POST/task, crash after durable accept before enqueue, late/ambiguous Batch create, competing runs, lost reconciliation event, cancellation/create race, missing/conflicting chunk, Batch success with absent manifest, and worker death during a sample. Record actual outcomes and the compliance blocker; do not claim synthetic recovery proves SDK recovery.
- Offline: `scripts/test_offline.sh` launches the exact digest with `--gpus all --network none`, approved fixture mounted read-only at `/data`, writable output location matching the verified launcher, and no mounted model cache or cloud credentials. Then run the required A30 scenario and matching full deterministic replays. Exact Docker invocation waits for organizer launcher details.

Retain the original handoff's planning windows without treating them as completed milestones: November 1–4 for model comparison; November 5–9 for measured grounding; November 10–13 for measured performance work and any separately gated residual post-training; November 14–16 for the release rehearsal and freeze. SDK and initial baseline windows were October 28 and October 29–31. Delays or unavailable approvals require reprioritization, not skipped gates. The solution is due November 16 at 23:59 GMT+7; private input is released November 20 at 09:00, with frozen-solution results due November 23 at 23:59 GMT+7. Recheck the portal before submission. No optional platform work, tournament or LoRA may consume final offline/target verification; private release is not a pre-freeze dependency.

## 7. Cost, observability and operating limits

Start in `asia-southeast1`, one active on-demand L4 job, explicit task timeout, reviewed retry count, no standby GPU. `g2-standard-4` is only a measured memory-fit candidate: it has 16 GiB host RAM; use `g2-standard-8` if loading/runtime exceeds that, and `-16` only when CPU/RAM profiling warrants it. All three have one 24 GB L4. Use a G2-supported boot disk, not `pd-standard`. [G2 specifications](https://docs.cloud.google.com/compute/docs/accelerator-optimized-machines).

Cloud Run GPU Jobs are a simpler alternative for workloads safely under their one-hour per-attempt GPU timeout; do not build two schedulers. Keep Batch as default for longer evaluation/post-training. Change only after measured setup/runtime/cost makes the alternative preferable. [GPU job timeout](https://docs.cloud.google.com/run/docs/configuring/task-timeout).

No Singapore price or actual $300 balance was verified. Obtain the region-selected whole-VM price; do not add a second GPU price. Reserve per run: whole-VM hourly rate × ((1 + allowed retries) × task limit + startup/loading/cleanup allowance), plus disk, storage/operations, image registry, builds, logs, transfer and tax. Task timeout is not a total VM-lifetime or hard financial cap. Compare reservations against verified remaining eligible credit minus all existing spend/reserve. [Pricing](https://cloud.google.com/products/compute/pricing/accelerator-optimized), [calculator](https://cloud.google.com/products/calculator), [Batch pricing](https://cloud.google.com/batch/pricing).

Dispatcher enforces approved region/tier/digest/time/retry allowlists, one slot and reserved budget. Scheduler checks whole-run deadline and requests cancellation; operator investigates uncertain creation/cancellation. Billing alerts and application breakers reduce risk but cannot guarantee zero overage. Default unauthorized overage allowance is zero deliberate spend beyond verified funds.

Use structured, redacted logs and native Cloud Run/Batch metrics first. Persist evaluation metrics in manifests/Firestore summaries: approximate task score with provenance, call F1, state match, ASR WER/CER and critical slots, failure categories, p50/p95/max latency, cold load, VRAM and expected/observed resource cost. Do not log sample payloads or use per-sample Monitoring labels. Add minimal API/dispatch/worker spans only where they aid diagnosis; no separate Collector, Prometheus, Langfuse, BigQuery or GKE deployment.

`scripts/audit_cost.sh` must show job/VM/disk/image/storage inventory, cleanup status and billing-export/report lag. Results bucket retention and registry cleanup are explicit; retain release artifacts externally before credit expiry. No background warm GPU, automatic region failover or unbounded retries.

## 8. Approvals and next authorized action

Observed on 2026-10-30: the selected project was active with billing enabled, required APIs enabled and unused global/Singapore L4 quota; an authorized Cloud Shell produced the reviewed Terraform plans. The [connection guide](cloud-connection.md) and [foundation runbook](cloud-foundation.md) record scope and limitations. No persistent foundation/IAM apply, restricted cloud transfer or GPU workload was performed. Credit balance/expiry, current price, capacity, IAP setup, deployed services and A30 execution remain unverified.

Before ticket 14, the owner must review fresh plans for the named project, region and bucket inputs, including persistent resources, retention/cleanup, applicable IAM changes and cost categories, and explicitly authorize the permitted spend. Approval of those plans does not authorize restricted artifact transfer, GPU execution or publication: each needs its own recorded approval, and organizer rules govern data and SDK use. Obtain actual credit balance/expiry and regional pricing before setting a spend ceiling; request additional quota only if needed and authorized.

Next implementation action: fix the shared contracts, then prepare the private worker adaptation, ticket 03 qualification, web/API and dispatcher code in parallel with ticket 14's approval process. Do not transfer restricted material, apply cloud changes or run billable workloads without their separate approvals. Deployment follows the foundation and its reviewed IAM; then execute the smallest approved synthetic vertical slice and a bounded real evaluation. Keep ticket 02 with its existing owner and ticket 03 open until its acceptance criteria are met or explicitly revised by the team. Full mid-sample recovery remains blocked on compliant SDK semantics, and L4 development does not replace target-A30 release verification.
