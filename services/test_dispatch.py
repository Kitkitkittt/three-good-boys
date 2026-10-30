"""Dispatcher behaviour under injected fakes.

Each test names the fault it injects and the held state it expects. No Google
client is imported: the seams are the fakes below.
"""
import threading
import unittest

from lifemate_cloud.artifacts import InMemoryArtifactStore
from lifemate_cloud.errors import Conflict, IncompleteManifest
from lifemate_cloud.manifest import ManifestEntry, ResultManifest
from lifemate_cloud.requests import RunRequest
from lifemate_cloud.run import Run, RunState

from dispatcher.service import DispatchPolicy, DispatchService
from dispatcher.errors import AmbiguousOutcome, LedgerOverflow
from dispatcher.http import handle_dispatch, handle_reconcile, status_for
from dispatcher.records import RunOp, RunOpState
from dispatcher.store import DispatcherRepository, InMemoryManifestStore

from lifemate_api.views import redact


def request(**overrides):
    fields = dict(
        dataset_id="ds-1",
        dataset_hash="a" * 64,
        model_id="mdl-1",
        model_hash="b" * 64,
        mode="agent",
        decoding={"temperature": 0.0},
        benchmark_id="public-test",
        machine_type="g2-standard-8",
        region="asia-southeast1",
        timeout_seconds=1800,
        retry_allowance=0,
        source_sha="c" * 40,
        image_digest="sha256:" + "d" * 64,
        inputs={"models/mdl-1.bin": 1},
    )
    fields.update(overrides)
    return RunRequest(**fields)


class FakeClock:
    def __init__(self, now=1_000.0):
        self.value = now

    def now(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class FakeQueue:
    def __init__(self):
        self.calls = []

    def enqueue_dispatch(self, run_id):
        self.calls.append(run_id)
        return "tasks/1"


class FakeBatch:
    """In-memory Batch: records creates and deduplicates on the named job."""

    def __init__(self):
        self.jobs = {}
        self.creates = []
        self.cancels = []
        self.create_error = None
        self.cancel_error = None
        self.cancel_result = None

    def create_job(self, job_id, request_id, spec):
        self.creates.append((job_id, request_id, spec))
        if self.create_error is not None:
            raise self.create_error
        if job_id in self.jobs:
            existing = self.jobs[job_id]
            if existing["request_id"] != request_id:
                raise Conflict("job id reused with a different request identity")
            return existing["uid"]
        uid = f"uid-{len(self.jobs) + 1}"
        self.jobs[job_id] = {"uid": uid, "request_id": request_id, "state": "ACTIVE", "phase": "RUNNING"}
        return uid

    def get_job(self, job_id):
        job = self.jobs.get(job_id)
        return dict(job) if job else None

    def cancel_job(self, job_id):
        self.cancels.append(job_id)
        if self.cancel_error is not None:
            raise self.cancel_error
        if self.cancel_result is not None:
            return self.cancel_result
        job = self.jobs.get(job_id)
        if job is None:
            return None
        job["state"] = "CANCELLED"
        job["phase"] = "CANCELLED"
        return dict(job)


class FakeRuns:
    """Stands in for the API's durable repository (ticket 16)."""

    def __init__(self):
        self._runs = {}
        self._requests = {}
        self._specs = {}
        self._intents = {}
        self._artifacts = {}

    def get_run(self, run_id):
        return self._runs[run_id]

    def put_run(self, run):
        self._runs[run.run_id] = run
        return run

    def all_runs(self):
        return list(self._runs.values())

    def put_request(self, run_id, payload):
        self._requests[run_id] = payload

    def get_request(self, run_id):
        return self._requests[run_id]

    # The API store keeps accepted_at/deadline_seconds/expected_names alongside
    # the pinned request; the fakes expose the same readers the dispatcher uses.
    def accepted_at(self, run_id):
        return self._requests[run_id].get("accepted_at")

    def deadline_seconds(self, run_id):
        return self._requests[run_id].get("deadline_seconds")

    def get_expected_names(self, run_id):
        return tuple(self._requests[run_id].get("expected_names") or ()) or None

    def put_artifacts(self, run_id, entries):
        self._artifacts[run_id] = tuple(entries)

    def artifacts(self, run_id):
        return self._artifacts.get(run_id, ())

    def put_batch_spec(self, spec):
        self._specs[(spec.run_id, spec.attempt)] = spec

    def get_batch_spec(self, run_id, attempt):
        return self._specs.get((run_id, attempt))

    def put_intent(self, intent):
        self._intents[(intent.run_id, intent.attempt)] = intent

    def get_intent(self, run_id, attempt=1):
        return self._intents.get((run_id, attempt))

    def all_intents(self):
        return list(self._intents.values())


def harness(cost=500, required=("result/a.json", "result/b.json"), policy=None, deadline_seconds=None):
    runs = FakeRuns()
    artifacts = InMemoryArtifactStore()
    manifests = InMemoryManifestStore()
    clock = FakeClock()
    batch = FakeBatch()
    queue = FakeQueue()
    repository = DispatcherRepository(runs)
    service = DispatchService(
        repository,
        batch,
        queue,
        clock,
        artifacts,
        manifests=manifests,
        policy=policy or DispatchPolicy(budget=10_000),
    )
    run = Run(run_id="run-1", owner="alice", request_fingerprint=request().fingerprint())
    repository.put_run(run)
    runs.put_request(
        run.run_id,
        {"accepted_at": clock.now(), "deadline_seconds": deadline_seconds or 100, "expected_names": list(required)},
    )
    for name in required:
        artifacts.put_if_absent(name, b"payload")
    return service, repository, artifacts, manifests, clock, batch, queue, run


def pin(manifests, artifacts, run, names):
    """Publish the worker's manifest exactly as ticket 19 commits it."""
    document = ResultManifest.create(run.run_id, names)
    for name in names:
        head = artifacts.head(name)
        document = document.add(
            ManifestEntry(
                name=name, generation=head.generation, checksum=head.checksum, size=len(head.content)
            )
        )
    manifests.put(document)
    return document


def reach_succeeded(service, repository, batch, run):
    """Drive a run to Batch SUCCEEDED so reconcile has something to judge."""
    service.accept(run.run_id, 100)
    service.dispatch(run.run_id)
    job_id = repository.get_op(run.run_id).job_id
    batch.jobs[job_id]["state"] = "SUCCEEDED"
    batch.jobs[job_id]["phase"] = "SUCCEEDED"


class AdmissionTests(unittest.TestCase):

    def test_duplicate_delivery_creates_one_job(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness()
        service.accept(run.run_id, 100)
        service.dispatch(run.run_id)
        service.accept(run.run_id, 100)
        service.dispatch(run.run_id)
        self.assertEqual(len(batch.jobs), 1)
        self.assertEqual(len(repository.all_ops()), 1)
        self.assertEqual(len(batch.creates), 1)

    def test_second_run_cannot_claim_a_held_slot(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness()
        repository.put_run(Run(run_id="run-2", owner="bob", request_fingerprint="e" * 64))
        service.accept(run.run_id, 100)
        with self.assertRaises(Conflict):
            service.accept("run-2", 100)

    def test_over_budget_is_rejected_and_holds_nothing(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness(policy=DispatchPolicy(budget=50))
        with self.assertRaises(LedgerOverflow):
            service.accept(run.run_id, 100)
        self.assertTrue(repository.get_slot().is_free)

    def test_accept_does_not_touch_the_network(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness()
        service.accept(run.run_id, 100, enqueue=False)
        self.assertEqual(batch.jobs, {})
        self.assertEqual(queue.calls, [])  # enqueue is a separate, repairable step

    def test_lost_enqueue_is_repaired_by_the_reconciler(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness()
        service.accept(run.run_id, 100, enqueue=False)
        service.reconcile(run.run_id)
        self.assertEqual(queue.calls, [run.run_id])
        service.dispatch(run.run_id)
        self.assertEqual(len(batch.jobs), 1)

    def test_repeated_reconcile_of_a_live_job_creates_nothing(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness()
        service.accept(run.run_id, 100)
        service.dispatch(run.run_id)
        for _ in range(3):
            service.reconcile(run.run_id)
        self.assertEqual(len(batch.creates), 1)


class AmbiguityTests(unittest.TestCase):
    def test_ambiguous_create_holds_the_slot_and_alerts(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness()
        batch.create_error = RuntimeError("connection reset")
        service.accept(run.run_id, 100)
        with self.assertRaises(AmbiguousOutcome):
            service.dispatch(run.run_id)
        self.assertEqual(repository.get_slot().holder, run.run_id)
        self.assertEqual(repository.get_op(run.run_id).state, RunOpState.CREATING)
        self.assertTrue(repository.get_slot().alerts)

    def test_retry_after_ambiguity_reuses_the_same_identity(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness()
        batch.create_error = RuntimeError("connection reset")
        service.accept(run.run_id, 100)
        with self.assertRaises(AmbiguousOutcome):
            service.dispatch(run.run_id)
        batch.create_error = None
        service.dispatch(run.run_id)
        self.assertEqual(len(batch.jobs), 1)
        first, second = batch.creates[0], batch.creates[1]
        self.assertEqual(first[:2], second[:2])
        self.assertEqual(repository.get_op(run.run_id).state, RunOpState.ACTIVE)

    def test_ambiguous_cancel_keeps_the_slot_held(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness()
        service.accept(run.run_id, 100)
        service.dispatch(run.run_id)
        batch.cancel_error = RuntimeError("deadline exceeded")
        with self.assertRaises(AmbiguousOutcome):
            service.cancel(run.run_id)
        self.assertEqual(repository.get_slot().holder, run.run_id)
        self.assertNotEqual(repository.get_op(run.run_id).state, RunOpState.CANCELED)

    def test_cancel_without_a_terminal_state_keeps_the_slot(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness()
        service.accept(run.run_id, 100)
        service.dispatch(run.run_id)
        batch.cancel_result = {"uid": "uid-1", "state": "ACTIVE", "phase": "RUNNING"}
        service.cancel(run.run_id)
        self.assertEqual(repository.get_slot().holder, run.run_id)

    def test_confirmed_cancel_releases_the_slot(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness()
        service.accept(run.run_id, 100)
        service.dispatch(run.run_id)
        op = service.cancel(run.run_id)
        self.assertEqual(op.state, RunOpState.CANCELED)
        self.assertTrue(repository.get_slot().is_free)
        self.assertEqual(repository.get_run(run.run_id).state, RunState.CANCELED)

    def test_missing_job_after_create_holds_the_slot(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness()
        service.accept(run.run_id, 100)
        service.dispatch(run.run_id)
        batch.jobs.clear()
        with self.assertRaises(AmbiguousOutcome):
            service.reconcile(run.run_id)
        self.assertEqual(repository.get_slot().holder, run.run_id)

    def test_unconfirmed_create_is_never_invented(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness()
        service.accept(run.run_id, 100)
        op = repository.get_op(run.run_id)
        repository.put_op(op)  # still ACCEPTED: create never attempted
        service.reconcile(run.run_id)
        self.assertEqual(batch.jobs, {})
        self.assertEqual(repository.get_slot().holder, run.run_id)


class SuccessTests(unittest.TestCase):
    NAMES = ("result/a.json", "result/b.json")

    def test_batch_success_with_complete_manifest_succeeds_and_releases(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness(required=self.NAMES)
        reach_succeeded(service, repository, batch, run)
        pin(manifests, artifacts, run, self.NAMES)
        op = service.reconcile(run.run_id)
        self.assertEqual(op.state, RunOpState.SUCCEEDED)
        self.assertTrue(op.manifest_verified)
        self.assertTrue(repository.get_slot().is_free)
        self.assertEqual(repository.get_run(run.run_id).state, RunState.SUCCEEDED)

    def test_batch_success_without_a_manifest_never_succeeds(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness(required=self.NAMES)
        reach_succeeded(service, repository, batch, run)
        op = service.reconcile(run.run_id)  # worker wrote nothing
        self.assertEqual(op.state, RunOpState.FAILED)
        self.assertEqual(repository.get_run(run.run_id).state, RunState.FAILED)
        self.assertEqual(repository.get_slot().holder, run.run_id)

    def test_missing_artifact_fails_closed(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness(required=self.NAMES)
        reach_succeeded(service, repository, batch, run)
        pin(manifests, artifacts, run, self.NAMES)
        artifacts.drop_for_test("result/b.json")
        op = service.reconcile(run.run_id)
        self.assertEqual(op.state, RunOpState.FAILED)
        self.assertNotEqual(repository.get_run(run.run_id).state, RunState.SUCCEEDED)
        self.assertEqual(repository.get_slot().holder, run.run_id)

    def test_conflicting_artifact_fails_closed(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness(required=self.NAMES)
        reach_succeeded(service, repository, batch, run)
        # The worker's manifest records a checksum that does not match the
        # object actually stored: tampered or foreign, never success.
        document = ResultManifest.create(run.run_id, self.NAMES)
        for name in self.NAMES:
            head = artifacts.head(name)
            checksum = "0" * 64 if name == "result/b.json" else head.checksum
            document = document.add(
                ManifestEntry(name=name, generation=head.generation, checksum=checksum, size=len(head.content))
            )
        manifests.put(document)
        op = service.reconcile(run.run_id)
        self.assertEqual(op.state, RunOpState.FAILED)
        self.assertNotEqual(repository.get_run(run.run_id).state, RunState.SUCCEEDED)
        self.assertEqual(repository.get_slot().holder, run.run_id)

    def test_batch_failure_holds_the_slot_until_verified(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness()
        service.accept(run.run_id, 100)
        service.dispatch(run.run_id)
        job_id = repository.get_op(run.run_id).job_id
        batch.jobs[job_id]["state"] = "FAILED"
        op = service.reconcile(run.run_id)
        self.assertEqual(op.state, RunOpState.FAILED)
        self.assertEqual(repository.get_run(run.run_id).state, RunState.FAILED)


class ConcurrentAdmissionTests(unittest.TestCase):
    """Ticket 17: two deliveries race; exactly one may hold the slot."""

    def torn_harness(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness()
        repository.put_run(Run(run_id="run-2", owner="bob", request_fingerprint="e" * 64))

        class TearingRuns(FakeRuns):
            """The op write lands, the spec write fails: a crash mid-admission."""

            def put_batch_spec(self, spec):
                raise RuntimeError("crash between reserve and op")

        runs = TearingRuns()
        torn = DispatchService(DispatcherRepository(runs), batch, queue, clock, artifacts)
        torn.repository.put_run(run)
        runs.put_request(run.run_id, {"accepted_at": clock.now(), "deadline_seconds": 100})
        return torn

    def test_two_concurrent_deliveries_admit_one_run(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness()
        repository.put_run(Run(run_id="run-2", owner="bob", request_fingerprint="e" * 64))
        service.repository._runs.put_request(
            "run-2", {"accepted_at": clock.now(), "deadline_seconds": 100}
        )
        outcomes = {}
        start = threading.Barrier(2)

        def admit(run_id):
            start.wait()
            try:
                outcomes[run_id] = service.accept(run_id, 100).run_id
            except Conflict as exc:
                outcomes[run_id] = exc

        threads = [threading.Thread(target=admit, args=(run_id,)) for run_id in ("run-1", "run-2")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        winners = [run_id for run_id, result in outcomes.items() if result == run_id]
        losers = [result for result in outcomes.values() if isinstance(result, Conflict)]
        self.assertEqual(len(winners), 1, outcomes)
        self.assertEqual(len(losers), 1, outcomes)
        self.assertEqual(len(repository.all_ops()), 1)
        self.assertEqual(repository.get_op(winners[0]).run_id, winners[0])
        self.assertEqual(repository.get_slot().holder, winners[0])
        self.assertEqual(repository.get_slot().reservation.cost, 100)

    def test_crash_between_reserve_and_op_leaves_no_half_state(self):
        torn = self.torn_harness()
        with self.assertRaises(RuntimeError):
            torn.accept("run-1", 100)
        self.assertEqual(torn.repository.all_ops(), [])
        self.assertTrue(torn.repository.get_slot().is_free)
        self.assertIsNone(torn.repository.get_slot().reservation)


class SweepTests(unittest.TestCase):
    """Ticket 17: the sweep adopts API-accepted runs with no dispatcher op."""

    def test_accepted_run_without_an_op_is_enqueued_by_an_empty_sweep(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness()
        # API acceptance only: a run and its pinned request; the task was lost.
        self.assertEqual(repository.all_ops(), [])
        code, body = handle_reconcile(service, {})
        self.assertEqual(code, 200)
        self.assertEqual(set(body["runs"]), {run.run_id})
        # Admitted once (which enqueues) and then reconciled: a lost task is
        # retried, never admits a second job for the same run.
        self.assertEqual(queue.calls, [run.run_id, run.run_id])
        self.assertEqual(len(repository.all_ops()), 1)
        self.assertEqual(repository.get_op(run.run_id).state, RunOpState.ACCEPTED)
        self.assertEqual(repository.get_slot().holder, run.run_id)
        # No network create during admission: the task performs it.
        self.assertEqual(batch.creates, [])

    def test_one_failing_run_does_not_abort_the_sweep(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness()
        service.accept(run.run_id, 100, enqueue=False)
        service.dispatch(run.run_id)
        # A second op whose Batch read raises; the sweep must still reconcile run-1.
        repository._runs.put_request("run-2", {"accepted_at": clock.now(), "deadline_seconds": 100})
        repository.put_op(RunOp(run_id="run-2", attempt=1, job_id="job-broken",
                                request_id="r2", state=RunOpState.ACTIVE))

        def get_job(job_id):
            if job_id == "job-broken":
                raise RuntimeError("batch unavailable")
            return dict(batch.jobs[job_id])

        batch.get_job = get_job
        code, body = handle_reconcile(service, {})
        self.assertEqual(code, 200)
        self.assertEqual(body["runs"]["run-2"].split(":", 1)[0], "RUNTIMEERROR")
        self.assertEqual(body["runs"][run.run_id], RunOpState.ACTIVE.value)


class ReasonCodeTests(unittest.TestCase):
    """The failure reason is CODE[: detail]; the API view redacts against it."""

    def test_failed_batch_run_returns_the_code_and_a_redacted_detail(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness()
        service.accept(run.run_id, 100)
        service.dispatch(run.run_id)
        batch.jobs[repository.get_op(run.run_id).job_id]["state"] = "FAILED"
        service.reconcile(run.run_id)
        reason = repository.get_run(run.run_id).failure_reason
        self.assertEqual(reason, "BATCH_FAILED: batch FAILED")
        self.assertEqual(redact(reason),
                         {"code": "BATCH_FAILED", "summary": "the GPU job reported a failure"})

    def test_unverified_artifacts_use_the_code_not_free_text(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness()
        reach_succeeded(service, repository, batch, run)
        op = service.reconcile(run.run_id)
        self.assertEqual(op.state, RunOpState.FAILED)
        reason = repository.get_run(run.run_id).failure_reason
        self.assertEqual(reason, "INCOMPLETEMANIFEST: incompletemanifest")
        self.assertNotIn("result manifest", redact(reason)["summary"])

    def test_deadline_reason_carries_the_code(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness()
        service.accept(run.run_id, 100)
        service.dispatch(run.run_id)
        clock.advance(101)
        service.enforce_deadline(run.run_id)
        self.assertEqual(redact(repository.get_run(run.run_id).failure_reason)["code"],
                         "DEADLINE_EXCEEDED")


class DeadlineTests(unittest.TestCase):
    def test_deadline_cancels_the_run(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness()
        service.accept(run.run_id, 100)
        service.dispatch(run.run_id)
        clock.advance(101)
        op = service.enforce_deadline(run.run_id)
        self.assertEqual(op.state, RunOpState.CANCELED)
        self.assertTrue(repository.get_slot().is_free)
        self.assertEqual(repository.get_run(run.run_id).state, RunState.CANCELED)

    def test_deadline_holds_when_cancellation_is_ambiguous(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness()
        service.accept(run.run_id, 100)
        service.dispatch(run.run_id)
        batch.cancel_error = RuntimeError("timeout")
        clock.advance(101)
        op = service.enforce_deadline(run.run_id)
        self.assertNotEqual(op.state, RunOpState.CANCELED)
        self.assertEqual(repository.get_slot().holder, run.run_id)

    def test_deadline_not_reached_does_nothing(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness()
        service.accept(run.run_id, 100)
        service.dispatch(run.run_id)
        clock.advance(99)
        op = service.enforce_deadline(run.run_id)
        self.assertEqual(op.state, RunOpState.ACTIVE)

    def test_accepted_record_is_authoritative_over_the_policy_fallback(self):
        # A pinned accepted_at + deadline_seconds wins even when the run was
        # only just dispatched; the policy deadline is never mixed in.
        service, repository, artifacts, manifests, clock, batch, queue, run = harness()
        service.accept(run.run_id, 100)
        service.dispatch(run.run_id)
        clock.advance(50)  # before the policy's 3600s, after the record's 100s
        repository._runs.put_request(
            run.run_id,
            {"accepted_at": clock.now() - 200, "deadline_seconds": 100,
             "expected_names": ["result/a.json", "result/b.json"]},
        )
        op = service.enforce_deadline(run.run_id)
        self.assertEqual(op.state, RunOpState.CANCELED)

    def test_deadline_raises_when_no_record_or_fallback_exists(self):
        # Neither the accepted record nor the in-process accept stamp can bound
        # the run, so the dispatcher refuses rather than assuming "unbounded".
        service, repository, artifacts, manifests, clock, batch, queue, run = harness()
        service.accept(run.run_id, 100, enqueue=False)
        repository._runs.put_request(run.run_id, {"expected_names": ["result/a.json"]})
        service._accepted_at.clear()
        with self.assertRaises(IncompleteManifest):
            service.enforce_deadline(run.run_id)


class HttpTests(unittest.TestCase):
    def test_dispatch_handler_accepts_and_creates(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness()
        code, body = handle_dispatch(service, {"run_id": run.run_id, "cost": 100})
        self.assertEqual(code, 200)
        self.assertEqual(body["job_id"], repository.get_op(run.run_id).job_id)
        self.assertEqual(len(batch.jobs), 1)

    def test_reconcile_handler_sweeps_every_run(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness()
        service.accept(run.run_id, 100)
        service.dispatch(run.run_id)
        clock.advance(101)
        code, body = handle_reconcile(service, {})
        self.assertEqual(code, 200)
        self.assertEqual(body["runs"][run.run_id], RunOpState.CANCELED.value)

    def test_scheduler_sweep_settles_a_finished_job_before_its_deadline(self):
        """The sweep must reconcile live ops, not only enforce deadlines.

        Batch reports SUCCEEDED with a complete, verified manifest while the
        whole-run deadline is still in the future. Only the scheduler sweep
        runs; the run must finish SUCCEEDED and release the slot.
        """
        names = ("result/a.json", "result/b.json")
        service, repository, artifacts, manifests, clock, batch, queue, run = harness(required=names)
        service.accept(run.run_id, 100)
        service.dispatch(run.run_id)
        job_id = repository.get_op(run.run_id).job_id
        batch.jobs[job_id]["state"] = "SUCCEEDED"
        batch.jobs[job_id]["phase"] = "SUCCEEDED"
        pin(manifests, artifacts, run, names)
        clock.advance(1)  # well inside the 100s deadline
        code, body = handle_reconcile(service, {})
        self.assertEqual(code, 200)
        self.assertEqual(body["runs"][run.run_id], RunOpState.SUCCEEDED.value)
        self.assertEqual(repository.get_run(run.run_id).state, RunState.SUCCEEDED)
        self.assertTrue(repository.get_slot().is_free)

    def test_sweep_leaves_a_running_job_untouched(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness()
        service.accept(run.run_id, 100)
        service.dispatch(run.run_id)
        clock.advance(1)
        code, body = handle_reconcile(service, {})
        self.assertEqual(code, 200)
        self.assertEqual(body["runs"][run.run_id], RunOpState.ACTIVE.value)
        self.assertEqual(repository.get_slot().holder, run.run_id)

    def test_sweep_keeps_a_terminal_run_terminal(self):
        service, repository, artifacts, manifests, clock, batch, queue, run = harness()
        service.accept(run.run_id, 100)
        service.dispatch(run.run_id)
        job_id = repository.get_op(run.run_id).job_id
        batch.jobs[job_id]["state"] = "FAILED"
        batch.jobs[job_id]["phase"] = "FAILED"
        code, body = handle_reconcile(service, {})
        self.assertEqual(body["runs"][run.run_id], RunOpState.FAILED.value)
        # A second sweep must not escalate a failed op or release the slot.
        code, body = handle_reconcile(service, {})
        self.assertEqual(body["runs"][run.run_id], RunOpState.FAILED.value)
        self.assertEqual(repository.get_slot().holder, run.run_id)

    def test_ambiguous_error_maps_to_retryable_status(self):
        self.assertEqual(status_for(AmbiguousOutcome("x")), 503)
        self.assertEqual(status_for(ValueError("x")), 500)


if __name__ == "__main__":
    unittest.main()
