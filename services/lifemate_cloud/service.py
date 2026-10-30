"""Run submission: authorization, user-scoped idempotency, admission, cancellation."""
import dataclasses
import uuid

from .batch import BatchJobSpec
from .errors import Conflict, Unauthorized
from .roles import Action, require
from .run import Run, RunState


@dataclasses.dataclass
class SubmissionService:
    repository: object
    new_run_id: object = lambda: uuid.uuid4().hex

    def submit(self, user, role, key, request):
        """Accept a run. Same user+key+request returns the stored run; different request conflicts."""
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
        self.repository.put_idempotency_record(user, key, fingerprint, run.run_id)
        self.repository.put_run(run)
        return run

    def get(self, user, role, run_id):
        require(role, Action.READ_RUN)
        return self.repository.get_run(run_id)

    def admit(self, user, role, run_id, attempt):
        """Pin the Batch identity for one explicit attempt; retries reuse it."""
        run = self._owned(user, role, run_id, Action.SUBMIT_RUN)
        existing = self.repository.get_batch_spec(run.run_id, attempt)
        if existing is not None:
            return existing
        spec = BatchJobSpec.for_attempt(run.run_id, attempt, run.request_fingerprint)
        if run.state is RunState.QUEUED:
            self.repository.put_run(run.transition(RunState.SUBMITTING))
        self.repository.put_batch_spec(spec)
        return spec

    def cancel(self, user, role, run_id):
        """Record cancellation intent; the observed outcome arrives through reconcile."""
        run = self._owned(user, role, run_id, Action.CANCEL_RUN)
        return self.repository.put_run(run.request_cancel())

    def batch_spec(self, run_id, attempt):
        return self.repository.get_batch_spec(run_id, attempt)

    def all_batch_specs(self):
        return self.repository.all_batch_specs()

    def all_runs(self):
        return self.repository.all_runs()

    def _owned(self, user, role, run_id, action):
        require(role, action)
        run = self.repository.get_run(run_id)
        if run.owner != user:
            raise Unauthorized(f"run {run_id} belongs to another user")
        return run
