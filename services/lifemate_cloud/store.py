"""Storage seam for team/experiment/run/admission records.

Firestore adapter is ticket 16's; this file only fixes the interface and the
in-memory implementation that tests run against.
"""
from .batch import BatchJobSpec


class InMemoryRepository:
    """Test double for the Firestore collections described in the plan."""

    def __init__(self):
        self._runs = {}
        self._idempotency = {}
        self._batch_specs = {}

    def get_run(self, run_id):
        return self._runs[run_id]

    def put_run(self, run):
        self._runs[run.run_id] = run

    def all_runs(self):
        return list(self._runs.values())

    def idempotency_record(self, user, key):
        return self._idempotency.get((user, key))

    def put_idempotency_record(self, user, key, fingerprint, run_id):
        self._idempotency[(user, key)] = (fingerprint, run_id)

    def get_batch_spec(self, run_id, attempt):
        return self._batch_specs.get((run_id, attempt))

    def put_batch_spec(self, spec: BatchJobSpec):
        self._batch_specs[(spec.run_id, spec.attempt)] = spec

    def all_batch_specs(self):
        return list(self._batch_specs.values())
