"""Dispatch-side records: the singleton admission slot and per-run operations.

These are the collections the dispatcher owns; the run/request/batch-spec
records stay in ``lifemate_cloud`` (ticket 15) so the API and the dispatcher
read one identity.
"""

import dataclasses
from enum import Enum

from lifemate_cloud.errors import Conflict, InvalidTransition


class RunOpState(str, Enum):
    """Lifecycle of the dispatcher's work for one run.

    ACCEPTED   durable accept recorded, no create attempted yet
    CREATING   a create may have been issued; outcome not yet verified
    ACTIVE     Batch create confirmed
    SUCCEEDED  Batch terminal success *and* a complete verified manifest
    CANCELED   terminal cancellation confirmed against the real job
    """

    ACCEPTED = "accepted"
    CREATING = "creating"
    ACTIVE = "active"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


TERMINAL_OPS = frozenset({RunOpState.SUCCEEDED, RunOpState.FAILED, RunOpState.CANCELED})

# The slot is held for every non-terminal op, plus the terminal cases whose
# outcome is not yet trusted: a failure nobody verified must not free the GPU.
_HELD_TERMINAL = frozenset({RunOpState.FAILED, RunOpState.CANCELED})


@dataclasses.dataclass(frozen=True)
class Admission:
    """A budget reservation for one run."""

    run_id: str
    cost: int
    currency: str = "USD-cents"
    settled: bool = False
    released: bool = False


@dataclasses.dataclass(frozen=True)
class AdmissionSlot:
    """Project-wide singleton GPU slot.

    ``release_verified`` is the whole point: a terminal state is not enough to
    free the GPU, because an operator must have reconciled the real Batch
    outcome first. Ambiguous or unverified terminals keep ``holder`` set.
    """

    holder: str = None
    reservation: Admission = None
    release_verified: bool = False
    evidence: str = None
    alerts: tuple = ()

    @property
    def is_free(self):
        return self.holder is None and self.reservation is None

    def claim(self, run_id, cost, currency="USD-cents"):
        if not self.is_free:
            raise Conflict(f"GPU slot is held by {self.holder!r}")
        return dataclasses.replace(
            self,
            holder=run_id,
            reservation=Admission(run_id=run_id, cost=cost, currency=currency),
            release_verified=False,
            evidence=None,
        )

    def alert(self, message):
        return dataclasses.replace(self, alerts=self.alerts + (message,))

    def request_release(self, evidence):
        """Operator/reconciler marks the outcome verified; the slot stays held."""
        if self.holder is None:
            raise InvalidTransition("GPU slot is already free")
        return dataclasses.replace(self, release_verified=True, evidence=evidence)


@dataclasses.dataclass(frozen=True)
class RunOp:
    """Dispatcher progress for one accepted run."""

    run_id: str
    attempt: int
    job_id: str
    request_id: str
    state: RunOpState = RunOpState.ACCEPTED
    create_calls: int = 0
    batch_uid: str = None
    batch_phase: str = None
    create_completed: bool = False
    cancel_calls: int = 0
    terminal_reason: str = None
    manifest_verified: bool = False

    def with_create_intent(self):
        """Persist the intent *before* the network call can be observed."""
        return dataclasses.replace(
            self, state=RunOpState.CREATING, create_calls=self.create_calls + 1, create_completed=False
        )

    def with_job(self, uid):
        return dataclasses.replace(self, batch_uid=uid, state=RunOpState.ACTIVE, create_completed=True)

    def with_phase(self, phase):
        return dataclasses.replace(self, batch_phase=phase)

    def with_cancel_calls(self, calls):
        return dataclasses.replace(self, cancel_calls=calls)

    def finish(self, state, reason=None, manifest_verified=False):
        if state not in TERMINAL_OPS:
            raise InvalidTransition(f"{state} is not a terminal op state")
        return dataclasses.replace(
            self, state=state, terminal_reason=reason, manifest_verified=manifest_verified
        )

    def can_release_slot(self, slot):
        """Release only when the run is terminal *and* the outcome is verified."""
        if self.state not in TERMINAL_OPS:
            return False
        if slot.holder != self.run_id:
            return False
        if not slot.release_verified:
            return False
        if self.state is RunOpState.SUCCEEDED:
            return self.manifest_verified
        return True

