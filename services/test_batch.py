"""Batch job identity is deterministic per (run, attempt) and stable across retries."""
import unittest

from lifemate_cloud.batch import BatchJobSpec, job_id_for


class BatchIdentityTests(unittest.TestCase):
    def test_same_run_and_attempt_yields_one_identity(self):
        left = BatchJobSpec.for_attempt("run-1", 1, request_fingerprint="f" * 64)
        right = BatchJobSpec.for_attempt("run-1", 1, request_fingerprint="f" * 64)
        self.assertEqual(left, right)
        self.assertEqual(left.request_id, right.request_id)

    def test_retries_inside_one_attempt_reuse_the_identity(self):
        first = BatchJobSpec.for_attempt("run-1", 1, request_fingerprint="f" * 64)
        retry = first.with_retry(1).with_retry(2)
        self.assertEqual(first.job_id, retry.job_id)
        self.assertEqual(first.request_id, retry.request_id)
        self.assertEqual(retry.attempt, 1)

    def test_distinct_attempts_and_runs_do_not_collide(self):
        ids = {
            BatchJobSpec.for_attempt(run, attempt, request_fingerprint="f" * 64).job_id
            for run in ("run-1", "run-2")
            for attempt in (1, 2, 3)
        }
        self.assertEqual(len(ids), 6)

    def test_a_different_request_in_the_same_attempt_gets_a_different_request_id(self):
        first = BatchJobSpec.for_attempt("run-1", 1, request_fingerprint="f" * 64)
        second = BatchJobSpec.for_attempt("run-1", 1, request_fingerprint="e" * 64)
        self.assertEqual(first.job_id, second.job_id)
        self.assertNotEqual(first.request_id, second.request_id)

    def test_job_id_is_a_legal_batch_name(self):
        spec = BatchJobSpec.for_attempt("run_1:attempt", 7, request_fingerprint="f" * 64)
        self.assertRegex(spec.job_id, r"^lmr-[a-z0-9][a-z0-9-]{0,60}$")
        self.assertEqual(spec.job_id, job_id_for("run_1:attempt", 7))

    def test_attempt_zero_or_negative_is_rejected(self):
        for attempt in (0, -1):
            with self.assertRaises(ValueError):
                BatchJobSpec.for_attempt("run-1", attempt, request_fingerprint="f" * 64)

    def test_request_id_is_uuid_shaped_and_stable(self):
        spec = BatchJobSpec.for_attempt("run-1", 1, request_fingerprint="f" * 64)
        self.assertRegex(spec.request_id, r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
        self.assertEqual(spec.request_id, BatchJobSpec.for_attempt("run-1", 1, request_fingerprint="f" * 64).request_id)


if __name__ == "__main__":
    unittest.main()
