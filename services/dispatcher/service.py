"""Dispatch: admission, durable accept, deterministic Batch create, reconciliation.

The rules this module exists to enforce (plan §4 "Durable lifecycle"):

* one project-wide GPU slot, held across provisioning, execution and every
  uncertain create/cancel outcome; queue concurrency is never the GPU control;
* create identity is fixed before the call and reused verbatim on retry, so a
  replay creates no second job;
* nothing is believed until the Batch API is read back: an ambiguous create or
  cancel holds the slot and alerts;
* ``SUCCEEDED`` requires Batch success *and* a manifest that verifies complete
  coverage — exit code or a partially written result is not success.

Failure reasons the dispatcher writes into the shared ``Run`` are ``CODE:
detail``; the API view redacts them against its fixed code table.
"""
import dataclasses
import datetime
import math

from lifemate_cloud.batch import BatchJobSpec
from lifemate_cloud.errors import Conflict, IncompleteManifest, InvalidTransition, ManifestConflict
from lifemate_cloud.run import RunState

from .errors import AmbiguousOutcome, LedgerOverflow, code_for
from .records import AdmissionSlot, RunOp, RunOpState
from .store import InMemoryManifestStore


def _accepted_timestamp(value):
    """Decode API UTC ISO timestamps while retaining numeric-seconds fixtures."""
    try:
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            accepted = datetime.datetime.fromisoformat(value)
            if accepted.utcoffset() != datetime.timedelta(0):
                raise ValueError("accepted_at must be UTC")
            seconds = accepted.timestamp()
        if not math.isfinite(seconds):
            raise ValueError("accepted_at must be finite")
        return seconds
    except (TypeError, ValueError, OverflowError) as exc:
        raise IncompleteManifest("accepted_at must be UTC ISO 8601 or numeric seconds") from exc


@dataclasses.dataclass(frozen=True)
class DispatchPolicy:
    """Cost and deadline limits the dispatcher enforces, not the caller."""

    budget: int = 10_000
    currency: str = "USD-cents"
    deadline_seconds: int = 3_600

    def __post_init__(self):
        if isinstance(self.budget, bool) or not isinstance(self.budget, int) or self.budget < 0:
            raise ValueError("budget must be a non-negative int")
        if not isinstance(self.deadline_seconds, int) or self.deadline_seconds <= 0:
            raise ValueError("deadline_seconds must be a positive int")


class DispatchService:
    """Admission and reconciliation over injected seams."""

    def __init__(self, repository, batch, queue, clock, artifacts, manifests=None, policy=None, prefix=""):
        self.repository = repository
        self.batch = batch
        self.queue = queue
        self.clock = clock
        self.artifacts = artifacts
        self.manifests = manifests or InMemoryManifestStore()
        self.policy = policy or DispatchPolicy()
        self.prefix = prefix
        self._accepted_at = {}

    # -- admission ---------------------------------------------------------

    def accept(self, run_id, cost, attempt=1, enqueue=True):
        """Atomically claim the singleton slot + budget and persist create intent.

        No network happens here: the enqueue and the Batch create are separate
        steps so a crash between them is repairable. The read-check-write of the
        slot is one repository unit (``claim_slot``), so two concurrent
        deliveries cannot both see a free slot.
        """
        if isinstance(cost, bool) or not isinstance(cost, int) or cost < 0:
            raise ValueError("cost must be a non-negative int")
        run = self.repository.get_run(run_id)
        existing = self._op_or_none(run_id)
        if existing is not None:
            # Duplicate delivery: one accepted job, never a second one.
            if enqueue and existing.state is RunOpState.ACCEPTED:
                self.queue.enqueue_dispatch(run_id)
            return existing
        if self._accepted_at.get(run_id) is not None:
            return self.repository.get_op(run_id)

        slot = self.repository.get_slot()
        if not slot.is_free:
            raise Conflict(f"GPU slot is held by {slot.holder!r}; queue is not a GPU control")
        if slot.reservation is not None and not slot.reservation.settled:
            raise LedgerOverflow("a previous budget reservation was never settled")
        if cost > self.policy.budget:
            raise LedgerOverflow(f"cost {cost} exceeds the admitted budget {self.policy.budget}")

        # The create intent is committed before any call that may be observed
        # after a crash, and the ledger is charged in the same unit.
        spec = BatchJobSpec.for_attempt(run_id, attempt, run.request_fingerprint)
        op = RunOp(run_id=run_id, attempt=attempt, job_id=spec.job_id, request_id=spec.request_id)
        submitted = run.transition(RunState.SUBMITTING) if run.state is RunState.QUEUED else None
        try:
            self.repository.claim_slot(run_id, cost, spec, op, run=submitted,
                                       currency=self.policy.currency)
        except Conflict:
            raise
        except Exception as exc:
            # The repository is responsible for all-or-nothing writes; this
            # keeps the recorded reason a code even if an adapter breaks that.
            self.repository.put_run(self._fail_run(run_id, f"{code_for(exc)}: admission failed"))
            raise
        # Stamped before any enqueue can fail: a task redelivered to this
        # instance finds the acceptance recorded and never re-enqueues.
        self._accepted_at[run_id] = self.clock.now()
        self.repository.audit(run_id, "accepted", {"job_id": spec.job_id, "cost": cost})
        if enqueue:
            try:
                self.queue.enqueue_dispatch(run_id)
            except Exception as exc:
                # The op is ACCEPTED and durable; the repair pass and the sweep
                # re-issue the task rather than failing a committed admission.
                self.repository.audit(run_id, "enqueue_lost", {"error": str(exc)})
        return op

    # -- create ------------------------------------------------------------

    def dispatch(self, run_id):
        """Try once to create the job; on ambiguity hold the slot and alert."""
        op = self.repository.get_op(run_id)
        if op.state in (RunOpState.ACTIVE, RunOpState.SUCCEEDED, RunOpState.FAILED, RunOpState.CANCELED):
            return op
        # Persist the intent before the create call can be observed by an
        # operator or lost to a crash.
        op = op.with_create_intent()
        self.repository.put_op(op)
        try:
            created = self.batch.create_job(op.job_id, op.request_id, self._spec(run_id, op.attempt))
        except Exception as exc:  # ambiguous: the call MAY have landed
            self.repository.put_op(op)
            self._hold_and_alert(run_id, f"ambiguous create for {op.job_id}: {exc}")
            raise AmbiguousOutcome(f"create outcome unknown for {op.job_id}") from exc
        # A create returns ``(job_name, uid)``; a bare uid from an older adapter
        # is still accepted. ``uid`` may be empty on the create response even
        # though the job exists, so only a missing name is ambiguous.
        name, uid = created if isinstance(created, tuple) else (None, created)
        if not name and not uid:
            self.repository.put_op(op)
            self._hold_and_alert(run_id, f"create returned no job identity for {op.job_id}")
            raise AmbiguousOutcome(f"create returned no job identity for {op.job_id}")
        self.repository.put_job_uid_index(op.job_id, uid)
        op = op.with_job(uid or name)
        self.repository.put_op(op)
        run = self.repository.get_run(run_id)
        if run.state is RunState.SUBMITTING:
            self.repository.put_run(run.transition(RunState.ACTIVE))
        self.repository.audit(run_id, "created", {"job_id": op.job_id, "name": name, "uid": uid})
        return op

    # -- reconciliation ----------------------------------------------------

    def reconcile(self, run_id):
        """Read the real Batch state, repair the enqueue, enforce the deadline."""
        op = self.repository.get_op(run_id)
        # A create that was never confirmed is a lost enqueue, not a reason to
        # make a second job: re-issue the dispatch task when it was lost. An op
        # that already exists means the task arrived and died here, so finish
        # the create with the same pinned identity.
        if op.state is RunOpState.ACCEPTED:
            if self.repository.get_intent(run_id, op.attempt) is None:
                self.queue.enqueue_dispatch(run_id)
                return op
            return self.dispatch(run_id)
        if op.state in (RunOpState.SUCCEEDED, RunOpState.FAILED, RunOpState.CANCELED):
            return op

        observed = self.batch.get_job(op.job_id)
        if observed is None:
            if op.state is RunOpState.ACTIVE and op.batch_uid is not None:
                # The job existed; it is gone without a terminal record.
                self._hold_and_alert(run_id, f"job {op.job_id} disappeared; slot held")
                raise AmbiguousOutcome(f"job {op.job_id} missing")
            # Create has not been confirmed yet: never invent one.
            return op
        if op.batch_uid is None and observed.get("uid"):
            self.repository.put_job_uid_index(op.job_id, observed["uid"])
            op = op.with_job(observed["uid"])
        phase = observed.get("phase")
        op = op.with_phase(phase)
        self.repository.put_op(op)

        if observed.get("state") == "SUCCEEDED":
            return self._finalize_success(run_id, op)
        if observed.get("state") in ("FAILED", "CANCELLED", "CANCELED"):
            # Terminal failure, but nobody has reconciled it yet: hold the
            # slot; an operator/reconciler must verify before release.
            state = observed.get("state")
            reason = f"BATCH_FAILED: batch {state}"
            op = op.finish(RunOpState.FAILED, reason=reason)
            self.repository.put_op(op)
            self.repository.put_run(self._fail_run(run_id, reason))
            self._hold_and_alert(run_id, f"batch terminal {state}; awaiting verified release")
            return op
        if observed.get("state") == "SUCCEEDED":
            return self._finalize_success(run_id, op)
        return op

    def enforce_deadline(self, run_id):
        """Cancel a run once its whole-run deadline has elapsed."""
        deadline = self._deadline(run_id)
        if deadline is None or self.clock.now() <= deadline:
            return self.repository.get_op(run_id)
        try:
            self.cancel(run_id, reason="DEADLINE_EXCEEDED: deadline exceeded")
            return self.reconcile(run_id)
        except AmbiguousOutcome:
            # Ambiguous or unverified: the slot stays held for an operator.
            return self.repository.get_op(run_id)

    def _deadline(self, run_id):
        """Absolute deadline from the accepted run; policy is the fallback.

        The API-owned ``accepted_at``/``deadline_seconds`` records are the
        authority. An injected fake that is not an API repository still works
        through either branch below: a pinned request carrying the fields, or the
        ``_accepted_at`` fallback stamped at accept time. When neither yields an
        absolute deadline the run cannot be bounded, so this raises rather than
        silently treating the run as unbounded.
        """
        request = self.repository.get_request(run_id)
        accepted_at = getattr(request, "accepted_at", None)
        seconds = getattr(request, "deadline_seconds", None)
        if accepted_at is None and isinstance(request, dict):
            accepted_at = request.get("accepted_at")
            seconds = request.get("deadline_seconds")
        if accepted_at is not None:
            return _accepted_timestamp(accepted_at) + float(
                seconds if seconds is not None else self.policy.deadline_seconds
            )
        try:
            accepted_at = self.repository.accepted_at(run_id)
        except (AttributeError, KeyError):
            accepted_at = None
        if accepted_at is not None:
            seconds = self.repository.deadline_seconds(run_id)
            return _accepted_timestamp(accepted_at) + float(
                seconds if seconds is not None else self.policy.deadline_seconds
            )
        base = self._accepted_at.get(run_id)
        if base is not None:
            return base + self.policy.deadline_seconds
        raise IncompleteManifest(f"run {run_id} has no accepted deadline record")

    # -- cancellation ------------------------------------------------------

    def cancel(self, run_id, reason="cancel requested"):
        """Record intent, request cancellation, then reconcile the real outcome."""
        op = self.repository.get_op(run_id)
        if op.state in (RunOpState.SUCCEEDED, RunOpState.FAILED, RunOpState.CANCELED):
            return op
        # Intent is recorded on the run before the cancel call can be observed.
        run = self.repository.get_run(run_id)
        if not run.cancel_requested:
            self.repository.put_run(run.request_cancel())
        if op.state is RunOpState.ACCEPTED:
            # Nothing was created: the run is cancelled and the slot may be
            # released as a verified outcome.
            op = op.finish(RunOpState.CANCELED, reason=reason)
            self.repository.put_op(op)
            self.repository.put_run(self._fail_run(run_id, reason, cancel=True))
            self._release_verified(run_id, f"cancelled before create: {reason}")
            return op
        try:
            outcome = self.batch.cancel_job(op.job_id)
        except Exception as exc:  # ambiguous: the request may or may not have landed
            self.repository.put_op(op.with_cancel_calls(op.cancel_calls + 1))
            self._hold_and_alert(run_id, f"ambiguous cancel for {op.job_id}: {exc}")
            raise AmbiguousOutcome(f"cancel outcome unknown for {op.job_id}") from exc
        op = op.with_cancel_calls(op.cancel_calls + 1)
        self.repository.put_op(op)
        if outcome is None:
            self._hold_and_alert(run_id, f"cancel returned no outcome for {op.job_id}")
            raise AmbiguousOutcome(f"cancel outcome unknown for {op.job_id}")
        if outcome.get("state") == "SUCCEEDED":
            # The job finished before the cancel landed: not a cancellation.
            return self.reconcile(run_id)
        if outcome.get("state") in ("CANCELLED", "CANCELED"):
            op = op.finish(RunOpState.CANCELED, reason=reason)
            self.repository.put_op(op)
            self.repository.put_run(self._fail_run(run_id, reason, cancel=True))
            self._release_verified(run_id, f"cancel confirmed: {reason}")
            return op
        # A cancel request that produced no terminal state keeps the slot.
        self._hold_and_alert(run_id, f"cancel for {op.job_id} not yet terminal")
        return op

    def sweep(self):
        """Run the scheduler sweep: adopt API-only accepted runs, reconcile ops.

        A run the API accepted whose dispatch task was lost has a pinned request
        and no op; admitting it here is what repairs it. Each run is isolated so
        one failing run never aborts the sweep, and every outcome is reported.
        """
        results = {}
        for run in self._unadmitted_runs():
            try:
                self.accept(run.run_id, 0)
                self.repository.audit(run.run_id, "swept_admission", {})
                op = self.repository.get_op(run.run_id)
                results[run.run_id] = op.state.value
            except Exception as exc:
                self.repository.audit(run.run_id, "sweep_failed", {"error": str(exc)})
                results[run.run_id] = f"{code_for(exc)}: {exc}"
        for op in self.repository.all_ops():
            try:
                current = self.enforce_deadline(op.run_id)
                if current.state is op.state:
                    current = self.reconcile(op.run_id)
                results[current.run_id] = current.state.value
            except Exception as exc:
                results[op.run_id] = f"{code_for(exc)}: {exc}"
        return results

    def _unadmitted_runs(self):
        """Accepted, non-terminal runs with a pinned request and no dispatcher op."""
        admitted = {op.run_id for op in self.repository.all_ops()}
        return [
            run for run in self.repository.all_runs()
            if run.run_id not in admitted
            and run.state not in (RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELED)
            and self._request_or_none(run.run_id) is not None
        ]

    def _request_or_none(self, run_id):
        try:
            return self.repository.get_request(run_id)
        except (KeyError, TypeError):
            return None


    # -- internals ---------------------------------------------------------

    def _finalize_success(self, run_id, op):
        try:
            # Missing, incomplete or misframed manifest: not a success.
            verified = self.artifacts.verify(self._manifest(run_id), prefix=self.prefix)
            # Publish verified artifact identity for API/dashboard read-back.
            # Inside the try: a persistence failure fails the run closed rather
            # than leaving SUCCEEDED without the metadata it depends on.
            self.repository.put_artifacts(run_id, verified.entries)
        except Exception as exc:
            # Batch said success, the artifacts do not back it up.
            return self._fail_and_hold(run_id, op, exc, "unverified artifacts")
        op = op.finish(RunOpState.SUCCEEDED, reason="SUCCEEDED: manifest verified",
                       manifest_verified=True)
        self.repository.put_op(op)
        run = self.repository.get_run(run_id)
        if run.state is RunState.ACTIVE:
            self.repository.put_run(run.transition(RunState.SUCCEEDED))
        self._release_verified(run_id, "verified success")
        return op

    def _fail_and_hold(self, run_id, op, exc, alert):
        """Terminal failure with an uppercase code; the slot stays held.

        ``failure_reason`` is ``CODE: detail`` so the API view's redaction keeps
        the fixed summary. The detail is the error type, never its message: a
        message can name restricted objects or carry a traceback.
        """
        reason = f"{code_for(exc)}: {code_for(exc).lower()}"
        op = op.finish(RunOpState.FAILED, reason=reason)
        self.repository.put_op(op)
        self.repository.put_run(self._fail_run(run_id, reason))
        self._hold_and_alert(run_id, f"{alert} for {run_id}: {exc}")
        return op

    def _manifest(self, run_id):
        """Read the run's pinned result manifest; absence is what fails closed."""
        manifest = self.manifests.read(run_id)
        if manifest is None:
            raise IncompleteManifest(f"run {run_id} has no result manifest")
        # The worker's claim must match server-approved coverage, not its own.
        expected = self._expected_names(run_id)
        if set(manifest.required) != set(expected):
            raise ManifestConflict(
                f"run {run_id} manifest covers {sorted(manifest.required)}, "
                f"server approved {sorted(expected)}"
            )
        return manifest.verify_complete()

    def _expected_names(self, run_id):
        """Server-approved coverage: the API's accepted records are the authority.

        Prefer the API-owned reader; an injected fake that lacks it falls back to
        the pinned request payload so the seam still works without the API store.
        """
        reader = getattr(self.repository, "get_expected_names", None)
        if reader is not None:
            names = reader(run_id)
        else:
            request = self.repository.get_request(run_id)
            names = getattr(request, "expected_names", None)
            if names is None and isinstance(request, dict):
                names = request.get("expected_names")
        if not names:
            raise IncompleteManifest(f"run {run_id} accepted request declares no expected names")
        return tuple(names)

    def _release_verified(self, run_id, evidence):
        slot = self.repository.get_slot()
        if slot.holder != run_id:
            raise InvalidTransition(f"slot is held by {slot.holder!r}, not {run_id!r}")
        # Release is an explicit act with recorded evidence, not a side effect
        # of a terminal-looking state.
        self.repository.put_slot(AdmissionSlot(evidence=evidence))
        self.repository.audit(run_id, "slot_released", {"evidence": evidence})

    def _hold_and_alert(self, run_id, message):
        slot = self.repository.get_slot().alert(message)
        self.repository.put_slot(slot)
        self.repository.audit(run_id, "held", {"reason": message})

    def _fail_run(self, run_id, reason, cancel=False):
        """Move the shared run record to its terminal state."""
        run = self.repository.get_run(run_id)
        target = RunState.CANCELED if cancel else RunState.FAILED
        return run.transition(target, reason=reason)

    def _op_or_none(self, run_id):
        try:
            return self.repository.get_op(run_id)
        except KeyError:
            return None

    def _spec(self, run_id, attempt):
        run = self.repository.get_run(run_id)
        return BatchJobSpec.for_attempt(run_id, attempt, run.request_fingerprint)
