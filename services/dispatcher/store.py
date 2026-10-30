"""Dispatcher-owned persistence, composed over the API's durable repository.

Collections the dispatcher *owns*: the singleton admission slot, per-run ops,
the job-uid index and audit events. Everything else — runs, canonical requests,
enqueue intents, batch specs — is read or written through the injected ``runs``
repository (ticket 16's ``ApiRepository``), so the API and dispatcher share one
identity and one Firestore layout.

A production adapter swaps this class for Firestore and keeps exactly these
methods.
"""
import dataclasses
import threading

from lifemate_cloud.errors import Conflict

from .records import Admission, AdmissionSlot, RunOp, RunOpState


def _slot_document(slot):
    """The stored shape of the singleton slot, shared by both adapters."""
    return {
        "holder": slot.holder,
        "reservation": dataclasses.asdict(slot.reservation) if slot.reservation else None,
        "release_verified": slot.release_verified,
        "evidence": slot.evidence,
        "alerts": list(slot.alerts),
    }


def _spec_document(spec):
    """The pinned Batch identity, in the API's ``batch_specs`` layout."""
    return {
        "job_id": spec.job_id,
        "request_id": spec.request_id,
        "run_id": spec.run_id,
        "attempt": spec.attempt,
        "request_fingerprint": spec.request_fingerprint,
        "retry_count": spec.retry_count,
    }


class DispatcherRepository:
    """Adds the dispatcher's collections over the API's repository."""

    def __init__(self, runs):
        self._runs = runs
        self._ops = {}
        self._uid_index = {}
        self._events = []
        self._slot = AdmissionSlot()
        # Admission reads the slot and writes slot+spec+op; the lock makes that
        # one unit so two deliveries cannot both observe a free slot.
        self._lock = threading.Lock()

    # -- shared records (tickets 15/16) -----------------------------------

    def get_run(self, run_id):
        return self._runs.get_run(run_id)

    def put_run(self, run):
        return self._runs.put_run(run)

    def all_runs(self):
        return self._runs.all_runs()

    def get_request(self, run_id):
        """The canonical accepted request; the dispatcher reads, never trusts input."""
        return self._runs.get_request(run_id)

    def get_expected_names(self, run_id):
        """Server-approved output coverage, read from the API-owned records."""
        return self._runs.get_expected_names(run_id)

    def accepted_at(self, run_id):
        """When the API accepted the run, for the whole-run deadline."""
        return self._runs.accepted_at(run_id)

    def deadline_seconds(self, run_id):
        """The API's accepted whole-run deadline in seconds, if recorded."""
        return self._runs.deadline_seconds(run_id)

    def put_artifacts(self, run_id, entries):
        """Publish verified artifact identity for API/dashboard read-back.

        Called only after a manifest verified complete, so metadata never
        describes unverified bytes. The API owns the stored shape.
        """
        return self._runs.put_artifacts(run_id, entries)

    def get_batch_spec(self, run_id, attempt):
        return self._runs.get_batch_spec(run_id, attempt)

    def put_batch_spec(self, spec):
        return self._runs.put_batch_spec(spec)

    def get_intent(self, run_id, attempt=1):
        return self._runs.get_intent(run_id, attempt)

    def all_intents(self):
        return self._runs.all_intents()

    # -- dispatcher collections -------------------------------------------

    def get_op(self, run_id):
        return self._ops[run_id]

    def put_op(self, op):
        self._ops[op.run_id] = op

    def all_ops(self):
        return list(self._ops.values())

    def get_slot(self):
        return self._slot

    def put_slot(self, slot):
        self._slot = slot

    def claim_slot(self, run_id, cost, spec, op, run=None, currency="USD-cents"):
        """Read-check-write admission in one unit; returns the claimed slot.

        ``run`` is the post-acceptance run record and shares the locked admission
        boundary with the spec, op and slot, matching the Firestore transaction.
        """
        with self._lock:
            if not self._slot.is_free:
                raise Conflict(f"GPU slot is held by {self._slot.holder!r}; queue is not a GPU control")
            self._runs.put_batch_spec(spec)
            if run is not None:
                self._runs.put_run(run)
            self._slot = self._slot.claim(run_id, cost, currency)
            self._ops[op.run_id] = op
        return self._slot

    def get_job_uid_index(self, job_id):
        return self._uid_index.get(job_id)

    def put_job_uid_index(self, job_id, uid):
        self._uid_index[job_id] = uid

    def audit(self, run_id, event, detail=None):
        self._events.append((run_id, event, detail))

    def events(self, run_id=None):
        return [row for row in self._events if run_id is None or row[0] == run_id]


def firestore_repository(client, runs):
    """Production adapter: the same four dispatcher collections, in Firestore.

    The client is injected so tests never construct it and imports never read
    credentials. Every method maps to one document, so a crash between the
    Firestore write and the Cloud Tasks or Batch call leaves a discoverable
    record. The API-owned records (runs, requests, specs) stay in ``runs``: one
    identity and one layout shared with ticket 16.
    """
    return FirestoreDispatcherRepository(client, runs)


class FirestoreDispatcherRepository:
    """Firestore-backed twin of :class:`DispatcherRepository`.

    Documents: ``dispatch_ops/{run_id}``, ``job_uids/{job_id}``, the singleton
    ``dispatch_slot/singleton``, and append-only ``dispatch_events`` rows.
    """

    def __init__(self, client, runs):
        self._client = client
        self._runs = runs
        self._ops = client.collection("dispatch_ops")
        self._uids = client.collection("job_uids")
        self._slot_document = client.collection("dispatch_slot").document("singleton")
        self._events = client.collection("dispatch_events")
        # Same decorator seam as the API repository: tests inject it so no
        # Google client is imported.
        self._transactional = getattr(runs, "_transactional", None)

    def _decorate(self, callback):
        decorate = self._transactional
        if decorate is None:
            from google.cloud import firestore  # imported lazily

            decorate = firestore.transactional
        return decorate(callback)

    # -- shared records (tickets 15/16): one layout, read through `runs` -----

    def get_run(self, run_id):
        return self._runs.get_run(run_id)

    def put_run(self, run):
        return self._runs.put_run(run)

    def all_runs(self):
        return self._runs.all_runs()

    def get_request(self, run_id):
        return self._runs.get_request(run_id)

    def get_expected_names(self, run_id):
        return self._runs.get_expected_names(run_id)

    def accepted_at(self, run_id):
        return self._runs.accepted_at(run_id)

    def deadline_seconds(self, run_id):
        return self._runs.deadline_seconds(run_id)

    def put_artifacts(self, run_id, entries):
        return self._runs.put_artifacts(run_id, entries)

    def get_batch_spec(self, run_id, attempt):
        return self._runs.get_batch_spec(run_id, attempt)

    def put_batch_spec(self, spec):
        return self._runs.put_batch_spec(spec)

    def get_intent(self, run_id, attempt=1):
        return self._runs.get_intent(run_id, attempt)

    def all_intents(self):
        return self._runs.all_intents()

    # -- dispatcher collections ---------------------------------------------

    def get_op(self, run_id):
        snapshot = self._ops.document(run_id).get()
        if not snapshot.exists:
            raise KeyError(run_id)
        return self._op_from(snapshot.to_dict())

    def put_op(self, op):
        self._ops.document(op.run_id).set(dataclasses.asdict(op))
        return op

    def all_ops(self):
        return [self._op_from(doc.to_dict()) for doc in self._ops.stream()]

    def get_slot(self):
        snapshot = self._slot_document.get()
        return self._slot_from(snapshot.to_dict()) if snapshot.exists else AdmissionSlot()

    def put_slot(self, slot):
        self._slot_document.set(_slot_document(slot))
        return slot

    def claim_slot(self, run_id, cost, spec, op, run=None, currency="USD-cents"):
        """Single transaction: write the submitting run, spec, op and holder.

        The transaction is the guarantee; a second delivery's read sees the
        committed holder, or its commit is retried against the winner. No Cloud
        Tasks or Batch call is made here.
        """
        spec_document = self._runs._specs.document(f"{spec.run_id}:{spec.attempt}")
        claimed = {}
        run_document = self._runs._runs.document(run_id) if run is not None else None

        @self._decorate
        def _commit(transaction):
            snapshot = self._slot_document.get(transaction=transaction)
            slot = self._slot_from(snapshot.to_dict()) if snapshot.exists else AdmissionSlot()
            if not slot.is_free:
                raise Conflict(f"GPU slot is held by {slot.holder!r}; queue is not a GPU control")
            # Read metadata before the first write, as required by Firestore.
            metadata = run_document.get(transaction=transaction).to_dict() if run_document else None
            claimed["slot"] = slot.claim(run_id, cost, currency)
            transaction.set(spec_document, _spec_document(spec))
            transaction.set(self._ops.document(op.run_id), dataclasses.asdict(op))
            transaction.set(self._slot_document, _slot_document(claimed["slot"]))
            if run_document is not None:
                transaction.set(run_document, self._runs._run_to(
                    run, metadata.get("accepted_at"), metadata.get("deadline_seconds")))

        _commit(self._client.transaction())
        return claimed["slot"]

    def get_job_uid_index(self, job_id):
        snapshot = self._uids.document(job_id).get()
        return snapshot.to_dict().get("uid") if snapshot.exists else None

    def put_job_uid_index(self, job_id, uid):
        self._uids.document(job_id).set({"uid": uid})

    def audit(self, run_id, event, detail=None):
        self._events.add({"run_id": run_id, "event": event, "detail": detail})

    def events(self, run_id=None):
        query = self._events
        if run_id is not None:
            query = query.where("run_id", "==", run_id)
        return [(doc.to_dict()["run_id"], doc.to_dict()["event"], doc.to_dict()["detail"])
                for doc in query.stream()]

    @staticmethod
    def _op_from(data):
        return RunOp(
            run_id=data["run_id"],
            attempt=int(data["attempt"]),
            job_id=data["job_id"],
            request_id=data["request_id"],
            state=RunOpState(data.get("state", RunOpState.ACCEPTED.value)),
            create_calls=int(data.get("create_calls", 0)),
            batch_uid=data.get("batch_uid"),
            batch_phase=data.get("batch_phase"),
            create_completed=bool(data.get("create_completed", False)),
            cancel_calls=int(data.get("cancel_calls", 0)),
            terminal_reason=data.get("terminal_reason"),
            manifest_verified=bool(data.get("manifest_verified", False)),
        )

    @staticmethod
    def _slot_from(data):
        reservation = data.get("reservation")
        return AdmissionSlot(
            holder=data.get("holder"),
            reservation=Admission(**reservation) if reservation else None,
            release_verified=bool(data.get("release_verified", False)),
            evidence=data.get("evidence"),
            alerts=tuple(data.get("alerts") or ()),
        )


class InMemoryManifestStore:
    """Test manifest store: the worker's pinned manifest, keyed by run ID."""

    def __init__(self):
        self._manifests = {}

    def put(self, manifest):
        self._manifests[manifest.run_id] = manifest

    def read(self, run_id):
        return self._manifests.get(run_id)
