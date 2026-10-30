"""Durable acceptance: one transaction persists run, idempotency and enqueue intent.

The enqueue itself (a Cloud Tasks call) happens after the transaction commits, so
a slow or failing network never holds a Firestore transaction open. If enqueue is
lost the intent survives and the reconciler (ticket 17) repairs it.
"""
import dataclasses
import enum
import uuid

from lifemate_cloud.batch import BatchJobSpec
from lifemate_cloud.errors import Conflict
from lifemate_cloud.roles import Action, require
from lifemate_cloud.run import Run


class IntentState(str, enum.Enum):
    PENDING = "PENDING"  # persisted, not yet enqueued
    ENQUEUED = "ENQUEUED"  # a task accepted the dispatch message


@dataclasses.dataclass(frozen=True)
class EnqueueIntent:
    run_id: str
    attempt: int
    job_id: str
    state: IntentState = IntentState.PENDING

    @classmethod
    def for_run(cls, run_id, request_fingerprint, attempt=1):
        return cls(
            run_id=run_id,
            attempt=int(attempt),
            job_id=BatchJobSpec.for_attempt(run_id, attempt, request_fingerprint).job_id,
        )

    def enqueued(self):
        return dataclasses.replace(self, state=IntentState.ENQUEUED)


@dataclasses.dataclass
class AcceptanceService:
    """Accepts a run and records the dispatch intent atomically.

    ``repository`` must offer ``commit_acceptance``: the Firestore adapter runs
    the run, idempotency and intent writes in one transaction. The real enqueuer
    is invoked by :meth:`enqueue` only after acceptance returns.
    """

    repository: object
    enqueuer: object = None
    new_run_id: object = lambda: uuid.uuid4().hex

    def accept(self, user, role, key, request, expected_names=(), deadline_seconds=None,
               accepted_at=None, experiment_id=None, benchmark=None):
        """Persist acceptance. Same user+key+request returns the stored run."""
        require(role, Action.SUBMIT_RUN)
        if not isinstance(key, str) or not key.strip():
            raise ValueError("idempotency key must be a non-empty string")
        fingerprint = request.fingerprint()
        record = self.repository.idempotency_record(user, key)
        if record is not None:
            stored_fingerprint, run_id = record
            if stored_fingerprint != fingerprint:
                raise Conflict(f"idempotency key {key!r} was used for a different request")
            return self.repository.get_run(run_id)
        run = Run(run_id=self.new_run_id(), owner=user, request_fingerprint=fingerprint)
        intent = EnqueueIntent.for_run(run.run_id, fingerprint)
        # The canonical request, coverage and deadline are persisted in the same
        # transaction so dispatch reads pinned server data, never the caller again.
        self.repository.commit_acceptance(
            user, key, fingerprint, run, intent, request,
            accepted_at=accepted_at, deadline_seconds=deadline_seconds,
            expected_names=expected_names, experiment_id=experiment_id,
            benchmark=benchmark,
        )
        return run

    def enqueue(self, run_id, attempt=1):
        """Dispatch the persisted intent outside any transaction. Idempotent.

        With no configured enqueuer nothing is sent and the intent stays PENDING
        for the reconciler to pick up.
        """
        intent = self.repository.get_intent(run_id, attempt)
        if intent is None:
            raise KeyError(f"no enqueue intent for run {run_id!r} attempt {attempt}")
        if intent.state is IntentState.ENQUEUED or self.enqueuer is None:
            return intent
        self.enqueuer.enqueue(intent)
        return self.repository.put_intent(intent.enqueued())

    def request_for(self, run_id):
        """The canonical request pinned at acceptance time."""
        return self.repository.get_request(run_id)

    def intents(self):
        return self.repository.all_intents()


@dataclasses.dataclass
class ProgressService:
    """Reconcile-side writes the dispatcher/worker own; the API only reads them."""

    repository: object

    def record_transition(self, run_id, target, reason=None):
        run = self.repository.get_run(run_id)
        return self.repository.put_run(run.transition(target, reason))
