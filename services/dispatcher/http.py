"""Machine-only HTTP surface: two POST handlers.

Minimal by design. The endpoints translate a small JSON body into one service
call and map domain errors to status codes; all behaviour lives in ``service``
so it is reachable (and tested) without an HTTP server. The real deployment
wraps these two callables in the framework of the runtime image.
"""
import json

from .errors import AmbiguousOutcome, DeadlineExceeded, LedgerOverflow

# 409 for a state that must not be forced; 503 for an outcome nobody verified,
# which the caller must retry with the same identity rather than a new one.
_STATUS = {
    AmbiguousOutcome: 503,
    DeadlineExceeded: 504,
    LedgerOverflow: 409,
}


def handle_dispatch(service, body):
    """POST /internal/dispatch: accept if new, then try the create exactly once."""
    payload = _json(body)
    run_id = payload["run_id"]
    cost = int(payload.get("cost", 0))
    attempt = int(payload.get("attempt", 1))
    service.accept(run_id, cost, attempt=attempt)
    op = service.dispatch(run_id)
    return 200, {"run_id": run_id, "state": op.state.value, "job_id": op.job_id}


def handle_reconcile(service, body):
    """POST /internal/reconcile: reconcile one run, or sweep for the scheduler."""
    payload = _json(body)
    run_id = payload.get("run_id")
    if run_id is not None:
        op = service.enforce_deadline(run_id)
        op = service.reconcile(run_id)
        return 200, {"run_id": run_id, "state": op.state.value, "phase": op.batch_phase}
    # Scheduler sweep: every recorded op takes the same deadline-then-reconcile
    # path as an explicit run, so a pre-deadline job that already finished (or
    # failed) is settled without waiting for its deadline. Both service calls
    # are safe on every state: ``enforce_deadline`` is a no-op when unexpired,
    # and ``reconcile`` returns early for ACCEPTED and for terminal ops.
    results = {}
    for op in service.repository.all_ops():
        current = service.enforce_deadline(op.run_id)
        current = service.reconcile(op.run_id) if current.state is op.state else current
        results[current.run_id] = current.state.value
    return 200, {"runs": results}


def _json(body):
    if isinstance(body, (bytes, bytearray)):
        return json.loads(body or b"{}")
    if isinstance(body, str):
        return json.loads(body or "{}")
    return body or {}


def status_for(error):
    """Map a dispatcher error to an HTTP status; 500 for anything unexpected."""
    for kind, code in _STATUS.items():
        if isinstance(error, kind):
            return code
    return 500
