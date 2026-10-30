"""Narrow seams the dispatcher depends on.

Every one is a protocol with an in-memory or trivial implementation so tests
inject fakes and exercise the *shared* dispatcher code. The Google adapters in
``google_adapters.py`` implement the same names and are imported by the entry
point only, never at module import time (plan §4: no client import here).
"""
import typing

@typing.runtime_checkable
class BatchClient(typing.Protocol):
    """The subset of the Batch API the dispatcher trusts.

    ``create_job`` may be OBSERVED AFTER A CRASH, so its outcome is never
    assumed: the dispatcher persists intent first and only believes the result
    after ``get_job`` agrees.
    """

    def create_job(self, job_id, request_id, spec):
        """Create one named job. Idempotent on request_id; never called speculatively."""

    def get_job(self, job_id):
        """Return the observed job: {'name','uid','phase','state'} or None if absent."""

    def cancel_job(self, job_id):
        """Request cancellation of a named job; return the observed outcome."""


@typing.runtime_checkable
class QueueClient(typing.Protocol):
    def enqueue_dispatch(self, run_id):
        """Ask for a dispatch; repair is re-entrant and task retries replay it."""


@typing.runtime_checkable
class Clock(typing.Protocol):
    def now(self):
        """Unix seconds, injected so deadlines are testable."""


@typing.runtime_checkable
class ArtifactStore(typing.Protocol):
    def verify(self, manifest, prefix=""):
        """Re-read every pinned generation; raise on missing or conflicting content."""


@typing.runtime_checkable
class DispatcherStore(typing.Protocol):
    def put_op(self, op):
        ...

    def get_op(self, run_id):
        ...

    def all_ops(self):
        ...

    def get_slot(self):
        ...

    def put_slot(self, slot):
        ...

    def get_job_uid_index(self, job_id):
        ...

    def put_job_uid_index(self, job_id, uid):
        ...

    def audit(self, run_id, event, detail=None):
        ...


