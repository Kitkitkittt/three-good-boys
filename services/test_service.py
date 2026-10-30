"""Submitting a run: user-scoped idempotency and authorization before any write."""
import unittest

from lifemate_cloud.batch import BatchJobSpec
from lifemate_cloud.errors import Conflict, Unauthorized
from lifemate_cloud.requests import RunRequest
from lifemate_cloud.roles import Role
from lifemate_cloud.run import RunState
from lifemate_cloud.service import SubmissionService
from lifemate_cloud.store import InMemoryRepository


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


def service():
    return SubmissionService(InMemoryRepository())


class SubmissionTests(unittest.TestCase):
    def test_first_submission_creates_a_queued_run(self):
        runs = service()
        run = runs.submit(user="alice", role=Role.RESEARCHER, key="k1", request=request())
        self.assertEqual(run.state, RunState.QUEUED)
        self.assertEqual(run.owner, "alice")
        self.assertEqual(runs.get("alice", Role.RESEARCHER, run.run_id), run)

    def test_same_key_and_request_returns_the_existing_run(self):
        runs = service()
        first = runs.submit(user="alice", role=Role.RESEARCHER, key="k1", request=request())
        second = runs.submit(user="alice", role=Role.RESEARCHER, key="k1", request=request())
        self.assertEqual(first.run_id, second.run_id)
        self.assertEqual(len(runs.all_runs()), 1)

    def test_same_key_different_request_conflicts_and_keeps_the_original(self):
        runs = service()
        first = runs.submit(user="alice", role=Role.RESEARCHER, key="k1", request=request())
        with self.assertRaises(Conflict):
            runs.submit(user="alice", role=Role.RESEARCHER, key="k1", request=request(region="us-central1"))
        self.assertEqual(len(runs.all_runs()), 1)
        self.assertEqual(runs.get("alice", Role.RESEARCHER, first.run_id), first)

    def test_idempotency_key_is_scoped_to_the_user(self):
        runs = service()
        alice = runs.submit(user="alice", role=Role.RESEARCHER, key="k1", request=request())
        bob = runs.submit(user="bob", role=Role.RESEARCHER, key="k1", request=request())
        self.assertNotEqual(alice.run_id, bob.run_id)
        self.assertEqual(len(runs.all_runs()), 2)

    def test_viewer_is_rejected_before_any_write(self):
        runs = service()
        with self.assertRaises(Unauthorized):
            runs.submit(user="vic", role=Role.VIEWER, key="k1", request=request())
        self.assertEqual(runs.all_runs(), [])

    def test_unauthorized_retry_does_not_consume_the_key(self):
        runs = service()
        with self.assertRaises(Unauthorized):
            runs.submit(user="vic", role=Role.VIEWER, key="k1", request=request())
        run = runs.submit(user="vic", role=Role.RESEARCHER, key="k1", request=request())
        self.assertEqual(run.state, RunState.QUEUED)

    def test_blank_key_is_rejected(self):
        for key in ("", "   "):
            with self.assertRaises(ValueError):
                service().submit(user="alice", role=Role.RESEARCHER, key=key, request=request())


class AdmissionTests(unittest.TestCase):
    def test_admit_pins_one_batch_identity_per_attempt(self):
        runs = service()
        run = runs.submit(user="alice", role=Role.RESEARCHER, key="k1", request=request())
        spec = runs.admit("alice", Role.RESEARCHER, run.run_id, attempt=1)
        self.assertEqual(spec, BatchJobSpec.for_attempt(run.run_id, 1, run.request_fingerprint))
        self.assertEqual(runs.get("alice", Role.RESEARCHER, run.run_id).state, RunState.SUBMITTING)
        self.assertEqual(runs.batch_spec(run.run_id, 1), spec)

    def test_admitting_the_same_attempt_twice_returns_the_same_identity(self):
        runs = service()
        run = runs.submit(user="alice", role=Role.RESEARCHER, key="k1", request=request())
        first = runs.admit("alice", Role.RESEARCHER, run.run_id, attempt=1)
        self.assertEqual(runs.admit("alice", Role.RESEARCHER, run.run_id, attempt=1), first)
        self.assertEqual(len(runs.all_batch_specs()), 1)

    def test_a_second_explicit_attempt_is_a_new_identity(self):
        runs = service()
        run = runs.submit(user="alice", role=Role.RESEARCHER, key="k1", request=request())
        first = runs.admit("alice", Role.RESEARCHER, run.run_id, attempt=1)
        second = runs.admit("alice", Role.RESEARCHER, run.run_id, attempt=2)
        self.assertNotEqual(first.job_id, second.job_id)

    def test_admission_requires_an_authorized_caller(self):
        runs = service()
        run = runs.submit(user="alice", role=Role.RESEARCHER, key="k1", request=request())
        with self.assertRaises(Unauthorized):
            runs.admit("vic", Role.VIEWER, run.run_id, attempt=1)
        self.assertEqual(runs.all_batch_specs(), [])

    def test_only_the_owner_may_admit_or_cancel_a_run(self):
        runs = service()
        run = runs.submit(user="alice", role=Role.RESEARCHER, key="k1", request=request())
        with self.assertRaises(Unauthorized):
            runs.admit("bob", Role.RESEARCHER, run.run_id, attempt=1)
        with self.assertRaises(Unauthorized):
            runs.cancel("bob", Role.RESEARCHER, run.run_id)

    def test_owner_may_cancel_a_run(self):
        runs = service()
        run = runs.submit(user="alice", role=Role.RESEARCHER, key="k1", request=request())
        runs.cancel("alice", Role.RESEARCHER, run.run_id)
        self.assertTrue(runs.get("alice", Role.RESEARCHER, run.run_id).cancel_requested)

    def test_unknown_run_is_not_found(self):
        with self.assertRaises(KeyError):
            service().get("alice", Role.RESEARCHER, "run-unknown")


if __name__ == "__main__":
    unittest.main()
