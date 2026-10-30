# 15: Shared cloud run contracts and persistence

**Parent spec:** [Shared Google Cloud platform #3](https://github.com/huyxdang/three-good-boys/issues/3).

**What to build:** One small Python package that owns request identity, run lifecycle, role authorization and Firestore/GCS adapters so the API, dispatcher and worker share one contract instead of three.

**Blocked by:** None for source code. Deployment needs [14](14-apply-google-cloud-foundation.md).

**Status:** ready-for-agent

**Owner:** omp-impl-cloud

**Progress:** done

## Implementation steps

1. Define the domain seam: canonical run request, idempotency identity, run states and legal transitions, role checks, Batch job naming and request identity, result manifest identity.
2. Define storage seams behind interfaces: Firestore repository for team/experiment/run/admission records and a GCS artifact interface for conditional create plus generation-pinned manifests.
3. Keep the implementation dependency-free of Google clients at import time so the domain and in-memory adapters run on any CPU host, and real adapters are supplied by the services.
4. Reuse the plan's contracts at [implementation plan §4](../../../docs/google-cloud-implementation-plan.md#4-minimum-api-and-job-contracts); do not duplicate them in code comments.

## Acceptance criteria

- [x] Same idempotency key and canonical request returns the existing run; same key with a different request conflicts.
- [x] Only legal state transitions are accepted; cancellation is an intent, not a terminal state.
- [x] Role checks reject unauthorized actions before any persistence write.
- [x] Batch identity is deterministic per run and attempt and is stable across retries.
- [x] A result is complete only when a manifest pins every object generation and checksum; conflicting content is refused.
- [x] In-memory adapters exercise the named contract rules without Google credentials or network; production adapters and concurrency behavior remain outside this contract-only ticket.

## Verification

Environment: Linux x64 CPU host, Python 3 stdlib only, no credentials and no network calls.

Command:

```
cd .worktrees/ticket-15-cloud-contracts && python3 -m unittest discover -s services -p 'test_*.py' -v
```

Historical result: `Ran 63 tests ... OK` (exit 0). Import of `lifemate_cloud.service`, `lifemate_cloud.artifacts` and `lifemate_cloud.manifest` succeeded with no Google client installed. Role-rejection tests inspect unchanged repository state; they do not establish that every production persistence implementation performs zero intermediate writes.

Evidence: `services/lifemate_cloud/` (contracts) and `services/test_*.py` (seams: `test_roles`, `test_requests`, `test_run`, `test_batch`, `test_manifest`, `test_artifacts`, `test_service`).

## Comments

- Production Firestore, Cloud Tasks and GCS adapters belong to tickets 16, 17 and 19; this ticket owns only the contracts and in-memory adapters.
- Integration review audit: contract scope is supported by `services/test_service.py`, `test_run.py`, `test_batch.py`, `test_manifest.py`, `test_artifacts.py` and `test_roles.py`. No claim of cloud deployment, transactional production admission or every possible cancellation race is made here; those belong to the dispatcher/deployment tickets.
