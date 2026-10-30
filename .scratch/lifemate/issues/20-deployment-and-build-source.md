# 20: Deployment and build source

**Parent spec:** [Shared Google Cloud platform #3](https://github.com/huyxdang/three-good-boys/issues/3).

**What to build:** The pinned container, deployment and operations source for the implemented services: Dockerfiles, reviewed Terraform for the actual Cloud Run services, Scheduler, IAM bindings and WIF, plus cost/offline/smoke scripts and one operations runbook.

**Blocked by:** [16](16-cloud-api-service.md), [17](17-cloud-dispatch-reconciliation.md), [18](18-cloud-team-dashboard.md), [19](19-cloud-worker-adapter.md) for real interfaces. No apply, image publication or restricted transfer under this ticket.

**Status:** ready-for-agent

**Owner:** omp-impl-deploy

**Progress:** blocked

## Implementation steps

1. Write separate Dockerfiles for api, web, worker and the offline submission image with pinned dependencies and explicitly different asset inventories.
2. Extend `infra/terraform/dev/` with the real services, Scheduler job, resource-scoped IAM bindings, WIF pool/provider and budget alerts. Keep identities that ticket 13 already creates; do not grant Owner/Editor.
3. Fill the base image, entrypoint and mount contract only as far as official guidance allows; leave unresolved launcher details explicitly unverified in the runbook.
4. Write `scripts/smoke_cloud.sh`, `scripts/test_offline.sh` and `scripts/audit_cost.sh` against explicitly selected resources, and `docs/cloud-operations.md`.

## Acceptance criteria

- [ ] Each Dockerfile builds an image that runs its service without embedded
      credentials, restricted data or model weights except in the submission
      image. API, web and worker builds were exercised historically; the submission
      image remains blocked on an approved private artifact context and launcher.
- [ ] Terraform validates and the authorized read-only plan is reviewed. Validation
      and mocked tests were exercised; no read-only plan was run because this
      environment has no Google credentials. No apply happened.
- [x] IAM bindings follow the plan's capability table with custom
      resource-scoped roles and grant no project-wide Owner or Editor.
- [ ] The actual offline submission image runs with no cloud client, credential or
      network. A network-disabled worker help command is not submission execution;
      the approved private launcher/SDK/models/wheelhouse and organizer launcher
      contract are missing.
- [x] Scripts refuse to run without an explicit project/region/target selection.
- [x] `docs/cloud-operations.md` covers deployment, artifact authorization,
      reconciliation, cancellation, incident handling and teardown, and states
      which launcher details remain unconfirmed.

## Verification

Environment: Linux x64, Python 3.14.4, Docker client/daemon 29.1.3, Terraform
1.13.4 (downloaded, not present on the host), no `nvidia-smi`, no Google
credentials, no `gcloud`.

```sh
# Containers (root build context, linux/amd64)
docker build -f services/lifemate_api/Dockerfile -t lifemate-api:source .       # Successfully tagged
docker build -f apps/web/Dockerfile -t lifemate-web:source .                   # Successfully tagged
docker build -f workers/gpu_eval/Dockerfile -t lifemate-worker:source .        # Successfully tagged
docker build -f submission/Dockerfile -t lifemate-submission:source .          # refuses: missing approved private artifacts (exit 1)
docker run --rm --entrypoint python lifemate-api:source -c "import fastapi, uvicorn, lifemate_api.server, dispatcher.server"   # api imports ok
docker run --rm --entrypoint python lifemate-worker:source -c "import importlib.metadata as m; print([...cloud dists...])"     # []
docker run --rm --network none --entrypoint python lifemate-worker:source -m workers.gpu_eval.main --help                       # exit 0

# Application tests
PYTHONPATH=services python3 -m unittest discover -s services -p 'test_*.py'    # Ran 172 tests, OK
node --test apps/web/test/*.test.ts                                           # pass 31, fail 0

# Terraform
terraform -chdir=infra/terraform/dev init -backend=false                       # google + google-beta 6.50.0 installed
terraform -chdir=infra/terraform/dev fmt -check                                # clean
terraform -chdir=infra/terraform/dev validate                                  # Success
terraform -chdir=infra/terraform/dev test                                      # 33 passed, 0 failed

# Scripts (refusal path)
env -u LIFEMATE_PROJECT -u GOOGLE_CLOUD_PROJECT -u LIFEMATE_REGION -u LIFEMATE_TARGET bash scripts/smoke_cloud.sh   # exit 2, "smoke_cloud: refusing: ..."
env -u ... bash scripts/test_offline.sh                                       # exit 2, "test_offline: refusing: ..."
env -u ... bash scripts/audit_cost.sh                                         # exit 2, "audit_cost: refusing: ..."
```

Explicitly unverified / environment-limited:

- No `terraform plan`: no credentials. The read-only-plan acceptance criterion is
  unmet in this environment; the owner must run it in an authorized workspace.
- No image was built for the submission package and no offline model execution
  ran: the approved private launcher/SDK/models/wheelhouse and the organizer
  launcher contract do not exist here. `scripts/test_offline.sh` therefore
  cannot pass end to end.
- Provider lock: google-beta `h1` hashes need `terraform providers lock` with
  network access to verify release signatures.
- Live GCS checksum verification, Batch create/cancel and IAP enforcement are
  apply-gated.

Contract fixes made while wiring the services (in scope as cutover):

- `services/dispatcher/queue.py` used an unsigned urllib POST that an
  IAM-private Cloud Run service rejects; it now creates a Cloud Tasks HTTP task
  with an OIDC token.
- `services/dispatcher/google_adapters.py` created a Batch job with no task
  groups or allocation policy; it now specifies runnables, volumes, machine
  type, boot disk and a worker identity separate from the machine invoker.
- `services/dispatcher/store.py` gained the Firestore-backed dispatcher
  repository (ops, slot, uid index, audit events); `entry.build_service` wires
  it, the manifest store and the real adapters.
- `services/lifemate_cloud/batch.py` gained `Mount` and `BatchJobConfig`, the
  approved execution contract (digest-pinned image, arguments, mounts).
- Artifact verification now hashes the pinned generation's bytes and compares
  sha256, instead of comparing GCS crc32c/md5 to a sha256 field.

## Comments

- `omp-impl-deploy` — Source implementation recorded on `ticket/20-deploy-source`,
  commit `2b369f6`. No apply, image publication or restricted transfer. Reopened
  during the integration review: `context/README.md:26` requires every acceptance
  criterion to hold before `done`; the read-only plan and actual submission-image
  build/offline execution remain blocked on the prerequisites named above.

- Integration acceptance (2026-10-30): `/tmp/tfbin/terraform -chdir=infra/terraform/dev validate && /tmp/tfbin/terraform -chdir=infra/terraform/dev test` passed: valid configuration and `33 passed, 0 failed`, using the existing provider cache without re-init. The corrected result IAM condition asserts both `manifests/` and the reviewed result prefix for dispatcher reads and worker create/read. `terraform fmt -check` identified `runtime_iam.tf`; `terraform fmt runtime_iam.tf` applied Terraform's source formatting. These local mocked results do not close the unchecked authorized plan or submission-image acceptance.
