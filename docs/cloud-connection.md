# Google Cloud connection and authorization

This is an authorized-team connection guide, not evidence that the proposed platform is deployed. The [implementation plan](google-cloud-implementation-plan.md) describes the proposed stack and its privacy boundaries; the observations below are dated snapshots. The [foundation runbook](cloud-foundation.md) owns Terraform and apply details.

## Observed state — 2026-10-30

The coordinator recorded these results for the selected project; they are a snapshot, not a guarantee of current access, price or capacity.

| Item | Observation |
| --- | --- |
| Project | `project-cc6075c8-508b-491d-98d`, number `388717445849`, lifecycle `ACTIVE`; selected region `asia-southeast1` (Singapore). |
| CLI identity | Active account `ttbeta8386@gmail.com`; a project IAM read returned `roles/owner`. This is the observed human/bootstrap identity, not a role to grant to application services. |
| Billing | Project billing was enabled and the linked billing account reported open. Neither actual credit balance/expiry nor Singapore pricing or authorized spend was established. |
| GPU quota | Global `GPUS_ALL_REGIONS`: limit 1, usage 0. Singapore `NVIDIA_L4_GPUS`: limit 1, usage 0. Quota is not a reservation or proof that L4 capacity is available. |
| APIs | The coordinator's project-scoped enable operation completed successfully for Compute Engine, Batch, Cloud Run, Artifact Registry, Cloud Build, Firestore, Cloud Tasks, Cloud Scheduler, IAM, IAM Credentials, Security Token Service, IAP, Secret Manager, Cloud Storage, Cloud Logging, Cloud Monitoring, Cloud Trace and Cloud Resource Manager. This is the enable-operation result; use the read-only service list below to inspect current state. |
| Cloud Shell | An authorized session reached Cloud Shell under the same account. Its project configuration was unset and `terraform` was not found in that initial session. Pass the project explicitly and check tool availability in the current workspace. |
| Resources | No GPU workload or persistent foundation/IAM apply was performed by this work. The earlier read-only inventory returned no VMs, persistent disks, reserved addresses or storage buckets at that time; it is not an exhaustive or ongoing guarantee that the project has no other resources. |

Enabling APIs and raising quota are cloud changes, not a foundation deployment. API enablement does not authorize later resource creation, IAM changes, spending or transfer of restricted material. Cloud Shell itself is a transient managed development environment; connecting may start it and configure SSH access.

The successful enable operation named these exact service IDs (some were already enabled):

```text
compute.googleapis.com                  batch.googleapis.com
run.googleapis.com                      artifactregistry.googleapis.com
cloudbuild.googleapis.com               firestore.googleapis.com
cloudtasks.googleapis.com               cloudscheduler.googleapis.com
iam.googleapis.com                      iamcredentials.googleapis.com
sts.googleapis.com                      iap.googleapis.com
secretmanager.googleapis.com            storage.googleapis.com
logging.googleapis.com                  monitoring.googleapis.com
cloudtrace.googleapis.com               cloudresourcemanager.googleapis.com
```

## CLI and Application Default Credentials

On the coordinator's Linux workstation, the installed CLI was `/home/dev-01/google-cloud-sdk/bin/gcloud`; it was **not on that session's `PATH`**. Use the absolute binary there, or use the `gcloud` already on `PATH` inside an authorized Cloud Shell. Paths and active accounts may differ on another machine.

`gcloud auth list` identifies CLI authentication. Terraform and Google client libraries usually resolve [Application Default Credentials (ADC)](https://cloud.google.com/docs/authentication/application-default-credentials), which are separate from CLI login; a successful `gcloud` command does not establish which identity ADC will use. The initial workstation probe found no default ADC file and no `GOOGLE_APPLICATION_CREDENTIALS` override. This does not establish ADC state in Cloud Shell or a future session.

If a workflow needs ADC, use an approved identity and authentication method in the authorized workspace. For example, the following checks whether ADC can obtain a token **without displaying it**; success does not identify the credential principal or its permissions:

```bash
/home/dev-01/google-cloud-sdk/bin/gcloud auth application-default print-access-token >/dev/null
```

ADC login or service-account impersonation is a separate credential/permission action, not part of the read-only checks below. Never print, save into the repository, upload or share access tokens, credential files, service-account keys or raw command output containing them. Do not assume a personal CLI login and ADC have the same account; verify the intended principal through the approved workspace/identity configuration.

## Read-only project checks

Run only as an authorized teammate. These commands query the explicit project; they do not enable APIs, change IAM, allocate compute or modify billing. They use `jq` to select the relevant quota metrics. `GCLOUD` is the coordinator's local path; in Cloud Shell set `GCLOUD=gcloud` instead.

```bash
GCLOUD=/home/dev-01/google-cloud-sdk/bin/gcloud
PROJECT=project-cc6075c8-508b-491d-98d
REGION=asia-southeast1

"$GCLOUD" auth list --filter=status:ACTIVE --format='value(account)'
"$GCLOUD" projects describe "$PROJECT" --format='yaml(projectId,projectNumber,lifecycleState)' --quiet
"$GCLOUD" billing projects describe "$PROJECT" --format='yaml(projectId,billingEnabled)' --quiet
"$GCLOUD" services list --enabled --project="$PROJECT" --format='value(config.name)' --quiet
"$GCLOUD" compute project-info describe --project="$PROJECT" --format='json(quotas)' --quiet \
  | jq '[.quotas[] | select(.metric == "GPUS_ALL_REGIONS")]'
"$GCLOUD" compute regions describe "$REGION" --project="$PROJECT" --format='json(name,quotas)' --quiet \
  | jq '{name, quotas: [.quotas[] | select(.metric == "NVIDIA_L4_GPUS")]}'
```

Compare the returned account and project with the intended authorization before proceeding. A billing-enabled result does not establish available credit, expiry, paid-account eligibility or spending approval. Quotas can change and cannot guarantee physical availability. Queries may fail if the account lacks permission; do not resolve this by granting broad roles without review.

## Authorized Cloud Shell

From the coordinator's workstation, use the absolute CLI path to run a project-scoped read-only command in the authorized Cloud Shell session:

```bash
/home/dev-01/google-cloud-sdk/bin/gcloud cloud-shell ssh --authorize-session \
  --project=project-cc6075c8-508b-491d-98d --quiet \
  --command="gcloud projects describe project-cc6075c8-508b-491d-98d --format='value(projectId,projectNumber,lifecycleState)' --quiet"
```

The outer `--project` selects the intended Cloud Shell context; the project is also explicit in the remote query because the earlier shell's default project was unset. `--authorize-session` authorizes the session and is not a general permission to run deployment commands. Cloud Shell connection can start the managed workspace and generate/use an SSH key; it is distinct from the read-only resource queries. Use approved GCP workspaces for development checks and builds. Only sanitized source/configuration may be transferred under the current authorization; no private code, data, model weights, traces or credentials may be uploaded. Do not publish terminal logs that may contain restricted material.

## Approval gates

1. **Billing and spend:** verify current credit, expiry, pricing and budget; obtain owner approval for any billing change or GPU/other billable workload. An enabled account, quota and billing alerts are not permission to spend or a hard cost cap.
2. **Persistent resources and IAM:** review the real Terraform plan, affected identities, data retention, cost categories and cleanup; obtain explicit owner approval before bootstrap/dev apply or IAM bindings. [Ticket 14](../.scratch/lifemate/issues/14-apply-google-cloud-foundation.md) is the apply gate; [ticket 13](../.scratch/lifemate/issues/13-google-cloud-foundation-plan.md) owns the plan.
3. **Restricted source and artifacts:** owner approval and applicable organizer permissions are required for the specific private workspace, source, data, SDK, weights and outputs before any transfer. Owner approval cannot override challenge rules. Do not upload the organizer environment tree, serialized ToolEnv state or historical private traces; never put raw audio, transcripts or tool results in normal logs.
4. **GPU and real-data execution:** separately approve a bounded job, region, machine, duration, retries, budget and artifact access; satisfy the existing Linux/NVIDIA and SDK gates before real inference. No standing GPU or automatic spend is authorized by quota alone.
5. **Release/publication:** obtain a separate owner and organizer-approved sharing decision before publishing a package or submitting. Target-A30 and network-disabled final-image proof remain independent of cloud setup.

Refer to the [decision order](decision-order.md) for measurement and model work, the [SDK contract](sdk-contract.md) for competition rules, and the [local ticket index](../.scratch/lifemate/README.md) for outstanding evidence. Never copy private traces, raw artifacts or credentials into tickets, docs, GitHub or public releases.
