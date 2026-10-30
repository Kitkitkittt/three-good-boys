# 17: Dispatch, admission and reconciliation

**Parent spec:** [Shared Google Cloud platform #3](https://github.com/huyxdang/three-good-boys/issues/3).

**What to build:** A machine-only service that turns accepted runs into one admitted Batch job, repairs lost enqueues, reconciles actual Batch state and enforces the whole-run deadline, cancellation and success rule.

**Blocked by:** [15](15-cloud-run-contracts-and-domain.md). Deployment and billable execution need [14](14-apply-google-cloud-foundation.md) plus reviewed IAM and workload approval.

**Status:** ready-for-agent

**Owner:** omp-impl-dispatch

**Progress:** blocked

## Implementation steps

1. Admit through one transaction that claims the singleton GPU slot and budget reservation, then create outside the transaction with deterministic identity.
2. Reconcile from the Batch API, never from notifications alone; release the slot only on a verified terminal outcome.
3. Treat cancellation as intent and reconcile the real result; hold the slot on ambiguous or missing jobs.
4. Mark success only when Batch succeeded and the artifact manifest verifies complete coverage.

## Acceptance criteria

- [x] Duplicate task delivery creates no second admitted job under concurrent admission. `DispatchService.accept` delegates to `repository.claim_slot`, which does the slot read-check-write in one unit: a lock in the in-memory repository, one Firestore transaction (slot, spec, op) in `FirestoreDispatcherRepository`. Tests: `test_dispatch.ConcurrentAdmissionTests.test_two_concurrent_deliveries_admit_one_run` (two threads, exactly one wins, loser gets `Conflict`, one op and one slot holder), `test_dispatch.ConcurrentAdmissionTests.test_crash_between_reserve_and_op_leaves_no_half_state` and `test_deployment_store.ApiLifecycleTests.test_claim_slot_is_all_or_nothing_with_an_unwritable_spec` (no half state), plus `test_two_claims_on_the_real_store_admit_one`.
- [x] Accept-then-lost-enqueue is repaired for API-only pending intents. `DispatchService.sweep` (the empty-body `/internal/reconcile`) iterates non-terminal runs that have a pinned request and no dispatcher op, admits them and enqueues their dispatch, then reconciles every live op. Each run is isolated; a failing run is reported as `CODE: detail` without aborting the sweep. Tests: `test_dispatch.SweepTests.test_accepted_run_without_an_op_is_enqueued_by_an_empty_sweep`, `test_dispatch.SweepTests.test_one_failing_run_does_not_abort_the_sweep`, `test_deployment_store.ApiLifecycleTests.test_sweep_repairs_an_api_accepted_run_with_a_lost_task` (real API acceptance records). Admission is the sweep's repair; the sweep does not re-read the API intent's own state, so an intent marked FAILED by another actor is still admitted.
- [x] Ambiguous create or cancel keeps the slot held rather than risking duplicate spend.
- [x] Missing or conflicting results never become success.
- [x] Queue concurrency is not used as a GPU concurrency control.

## Verification

Environment: Linux x64 CPU host, Python 3 stdlib only, no credentials, no network calls, no Google client installed.

Command:

```
cd .worktrees/ticket-17-cloud-dispatch && python3 -m unittest discover -s services -p 'test_*.py' -v
```

Result: `Ran 87 tests in 0.006s ... OK` (exit 0); 24 of them are the dispatcher suite in `services/test_dispatch.py`. `python3 -c "import dispatcher.entry"` succeeds with no Google SDK installed, proving the adapters are imported lazily.

Evidence: `services/dispatcher/` (`service` admission/create/reconcile/cancel; `records` slot and op state; `protocols` BatchClient/QueueClient/Clock/ArtifactStore seams; `store` repository and manifest store; `queue`/`google_adapters` thin production adapters; `http` two machine handlers; `entry` config wiring) and `services/test_dispatch.py`.

Injected faults exercised, each asserting a held non-success state: duplicate delivery (`test_duplicate_delivery_creates_one_job`), accept-then-lost-enqueue (`test_lost_enqueue_is_repaired_by_the_reconciler`), ambiguous create/cancel (`test_ambiguous_create_holds_the_slot_and_alerts`, `test_ambiguous_cancel_keeps_the_slot_held`), retry reuse (`test_retry_after_ambiguity_reuses_the_same_identity`), missing job after create (`test_missing_job_after_create_holds_the_slot`), Batch success with absent/missing/tampered manifest (`test_batch_success_without_a_manifest_never_succeeds`, `test_missing_artifact_fails_closed`, `test_conflicting_artifact_fails_closed`) and deadline cancel plus its ambiguous variant (`test_deadline_cancels_the_run`, `test_deadline_holds_when_cancellation_is_ambiguous`).

## Comments

- The dispatcher reads runs, canonical requests and enqueue intents through ticket 16's API repository (`get_run`, `get_request`, `get_intent`, `all_intents`) and explicitly delegates `accepted_at`, `deadline_seconds` and `get_expected_names`; it owns only the slot, per-run ops, job-uid index and audit events. Acceptance/deadline/coverage are persisted run metadata, not fields on `RunRequest`.
- Server-approved expected result coverage comes from the API's accepted record (`get_expected_names`); the worker manifest must match it, so a worker's own claim is never trusted as coverage. A fresh dispatcher instance enforces the persisted whole-run deadline; missing metadata without an in-instance acceptance fallback raises rather than disabling enforcement.
- Deployment, real Batch execution and billable GPU work remain gated on ticket 14 plus reviewed IAM and workload approval; no cloud call is made here.
- Integration review regressions use real `InMemoryApiRepository.commit_acceptance` records through `DispatcherRepository` plus `DispatchService`, not request dictionaries alone: deadline cancellation before/after the accepted deadline, otherwise-valid complete manifest success, and wrong expected-name coverage failure with the slot held. Deployment configuration construction uses the real `batch_config` and a synthetic environment whose keys exactly equal Terraform's `dispatcher_env`; consumer names are extracted from the actual functions in the test.
- Acceptance audit blocker: `DispatchService.accept` and the Firestore dispatcher store write admission state independently, so sequential fake tests do not prove concurrent singleton admission. API-only `PENDING` enqueue intents are not swept before a dispatcher op exists. These source gaps remain unchecked rather than being relabeled deployment limits. The scheduled Batch/deadline sweep is repaired separately in this integration; it does not close either gap above.
- Integration acceptance (2026-10-30): `python3 -m unittest discover -s services -p 'test_*.py' -v` passed `226` tests. `test_deployment_store.BatchConfigTests.test_terraform_dispatcher_env_matches_the_consumed_key_set` derives actual consumer keys and parses Terraform's env map; `BuildServiceTests.test_build_service_consumes_the_terraform_key_set` constructs the dispatcher with that exact key set and the real `batch_config` (external clients only are injected). API-store lifecycle tests enforce the accepted deadline and finalize correct coverage; Scheduler sweep tests reconcile completed jobs before deadline and preserve held failures. This closes the reviewed env/deadline/coverage/sweep bugs, not the unchecked admission/enqueue blockers.
- Explicit startup proof: `env PYTHONPATH=services python3 -m unittest test_deployment_store.BatchConfigTests.test_terraform_dispatcher_env_matches_the_consumed_key_set test_deployment_store.BuildServiceTests.test_build_service_consumes_the_terraform_key_set -v` passed `Ran 2 tests ... OK`. This parses Terraform's exact provided key set and constructs the production service with real Batch configuration; it would fail the original provider/consumer key mismatch. Final Terraform `fmt -check` exited 0.
- Dispatcher hardening (2026-10-30, branch `remediation/dispatcher-hardening`): admission is one `claim_slot` unit; the sweep adopts API-only accepted runs; failure reasons are now `CODE: detail` (`BATCH_FAILED`, `DEADLINE_EXCEEDED`, or the exception class in upper case, with the error type as detail, never its message) so `views.redact()` keeps its fixed summary and the API view needed no change; only the new uppercase code gained a summary entry. `create_app` serves `GET /healthz` with no service dependency, matching Terraform's startup probe. Evidence: `cd services && python3 -m unittest discover -s . -p 'test_*.py' -v` -> `Ran 241 tests ... OK (skipped=3)`; `/tmp/tfbin/terraform -chdir=infra/terraform/dev validate` -> `Success! The configuration is valid.`; `... terraform test` -> `Success! 33 passed, 0 failed.` Sequential duplicate delivery no longer re-enqueues: `accept` enqueues once after the admission commits, and `reconcile` of an `ACCEPTED` op re-issues the task only while no pinned intent records that it arrived.
