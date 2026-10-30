"""Run lifecycle: legal transitions, observed Batch phase, cancellation as intent."""
import dataclasses
from enum import Enum

from .errors import InvalidTransition


class RunState(str, Enum):
    QUEUED = "QUEUED"
    SUBMITTING = "SUBMITTING"
    ACTIVE = "ACTIVE"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


TERMINAL = frozenset({RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELED})

# The straight path is QUEUED -> SUBMITTING -> ACTIVE -> SUCCEEDED. Every live
# state may fail; CANCELED is only reachable after a cancel intent was recorded.
_TRANSITIONS = {
    RunState.QUEUED: {RunState.SUBMITTING},
    RunState.SUBMITTING: {RunState.ACTIVE},
    RunState.ACTIVE: {RunState.SUCCEEDED},
}
_CANCELABLE = frozenset({RunState.QUEUED, RunState.SUBMITTING, RunState.ACTIVE})


@dataclasses.dataclass(frozen=True)
class Run:
    run_id: str
    owner: str
    request_fingerprint: str
    state: RunState = RunState.QUEUED
    cancel_requested: bool = False
    batch_phase: str = None
    failure_reason: str = None

    def transition(self, target, reason=None):
        """Return the next run state; raise InvalidTransition if not legal."""
        target = RunState(target)
        if self.state in TERMINAL:
            raise InvalidTransition(f"run {self.run_id} is {self.state.value}")
        if target in (RunState.FAILED, RunState.CANCELED) and self.state in _CANCELABLE:
            return dataclasses.replace(self, state=target, failure_reason=reason)
        if target in _TRANSITIONS.get(self.state, ()):
            return dataclasses.replace(self, state=target, failure_reason=reason)
        raise InvalidTransition(f"run {self.run_id}: {self.state.value} -> {target.value}")

    def request_cancel(self):
        """Record cancellation intent without changing the run state."""
        if self.state in TERMINAL:
            raise InvalidTransition(f"run {self.run_id} is {self.state.value}")
        return dataclasses.replace(self, cancel_requested=True)

    def record_batch_phase(self, phase):
        """Store the observed Batch phase separately from the run state."""
        return dataclasses.replace(self, batch_phase=phase)
