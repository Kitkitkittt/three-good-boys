"""The run state machine; cancellation is an intent flag, never a terminal state."""
import unittest

from lifemate_cloud.errors import InvalidTransition
from lifemate_cloud.run import Run, RunState


def queued():
    return Run(run_id="run-1", owner="researcher-1", request_fingerprint="f" * 64)


class LifecycleTests(unittest.TestCase):
    def test_happy_path_is_queued_submitting_active_succeeded(self):
        run = queued()
        for target in (RunState.SUBMITTING, RunState.ACTIVE, RunState.SUCCEEDED):
            run = run.transition(target)
            self.assertEqual(run.state, target)
        self.assertFalse(run.cancel_requested)

    def test_transition_returns_a_new_run_and_leaves_the_old_one(self):
        run = queued()
        moved = run.transition(RunState.SUBMITTING)
        self.assertEqual(run.state, RunState.QUEUED)
        self.assertEqual(moved.state, RunState.SUBMITTING)

    def test_any_live_state_may_fail(self):
        for start in (RunState.QUEUED, RunState.SUBMITTING, RunState.ACTIVE):
            run = Run(run_id="r", owner="o", request_fingerprint="f", state=start)
            self.assertEqual(run.transition(RunState.FAILED).state, RunState.FAILED)

    def test_cancellation_is_intent_then_a_real_observed_outcome(self):
        run = queued().transition(RunState.SUBMITTING)
        intent = run.request_cancel().request_cancel()
        self.assertEqual(intent.state, RunState.SUBMITTING)
        self.assertTrue(intent.cancel_requested)
        canceled = intent.transition(RunState.CANCELED)
        self.assertEqual(canceled.state, RunState.CANCELED)
        self.assertTrue(canceled.cancel_requested)

    def test_cancel_intent_survives_a_run_that_succeeded_first(self):
        run = queued().transition(RunState.SUBMITTING).transition(RunState.ACTIVE).request_cancel()
        self.assertEqual(run.transition(RunState.SUCCEEDED).state, RunState.SUCCEEDED)

    def test_terminal_states_reject_further_motion(self):
        for terminal in (RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELED):
            run = Run(run_id="r", owner="o", request_fingerprint="f", state=terminal)
            for target in RunState:
                with self.assertRaises(InvalidTransition, msg=(terminal, target)):
                    run.transition(target)
            with self.assertRaises(InvalidTransition):
                run.request_cancel()

    def test_skipping_states_is_rejected(self):
        run = queued()
        with self.assertRaises(InvalidTransition):
            run.transition(RunState.ACTIVE)
        run = run.transition(RunState.SUBMITTING)
        with self.assertRaises(InvalidTransition):
            run.transition(RunState.SUCCEEDED)

    def test_observed_batch_phase_is_separate_from_run_state(self):
        run = queued().record_batch_phase("PENDING")
        self.assertEqual(run.state, RunState.QUEUED)
        self.assertEqual(run.batch_phase, "PENDING")

    def test_batch_failure_is_never_success(self):
        run = Run(run_id="r", owner="o", request_fingerprint="f", state=RunState.ACTIVE)
        run = run.transition(RunState.FAILED, reason="batch task failed")
        self.assertEqual(run.failure_reason, "batch task failed")


if __name__ == "__main__":
    unittest.main()
