"""Storage seams the API needs on top of the ticket-15 repository.

Keyed by run id so a reader (dispatcher, ticket 17) can fetch:
- ``runs/{run_id}``: the ticket-15 :class:`Run`, plus API-owned ``accepted_at`` and
  ``deadline_seconds`` used for the whole-run deadline.
- ``requests/{run_id}``: the canonical :class:`RunRequest` payload pinned at
  acceptance, including the server-approved ``expected_names`` (result coverage).
- ``enqueue_intents/{run_id}:{attempt}``: the dispatch intent the reconciler repairs.
- ``idempotency/{sha256(user \\x00 key)}``: user-scoped idempotency record.
- ``experiments/{experiment_id}``: a created experiment instance (template binding).
- ``experiment_idempotency/{sha256(user \\x00 key)}``: user-scoped creation record.
- ``batch_specs/{run_id}:{attempt}``: the pinned Batch identity per attempt.

The in-memory implementation is a test double; ``firestore_repository`` is the
production adapter and imports its Google client lazily, so importing this module
needs no credentials.
"""
import hashlib

from lifemate_cloud.errors import Conflict
from lifemate_cloud.requests import RunRequest
from lifemate_cloud.store import InMemoryRepository


def idempotency_key(user, key):
    """A Firestore-safe document id for a user-scoped idempotency key."""
    return hashlib.sha256(f"{user}\0{key}".encode()).hexdigest()


class InMemoryApiRepository(InMemoryRepository):
    """Test double adding atomic acceptance, intents, requests and run metadata."""

    def __init__(self):
        super().__init__()
        self._intents = {}
        self._requests = {}
        self._accepted_at = {}
        self._deadlines = {}
        self._expected = {}
        self._runs_experiment = {}
        self._instances = {}
        self._artifacts = {}
        self._benchmarks = {}
        self._creation = {}
        self.commits = 0

    def put_run(self, run):
        self._runs[run.run_id] = run
        return run

    def commit_acceptance(self, user, key, fingerprint, run, intent, request, accepted_at=None,
                          deadline_seconds=None, expected_names=(), experiment_id=None,
                          benchmark=None):
        """One transaction: idempotency, run, pinned request, coverage and intent.

        ``benchmark`` is the ``(content_hash, cases)`` pair the template pinned at
        acceptance. It is stored with the run so a later catalog edit never
        rewrites the identity of a run already accepted.
        """
        self.commits += 1
        if (user, key) in self._idempotency:
            raise ValueError("acceptance committed twice for the same key")
        self._idempotency[(user, key)] = (fingerprint, run.run_id)
        self._runs[run.run_id] = run
        self._requests[run.run_id] = request.payload()
        self._intents[(run.run_id, intent.attempt)] = intent
        self._accepted_at[run.run_id] = accepted_at
        self._deadlines[run.run_id] = deadline_seconds
        self._expected[run.run_id] = tuple(expected_names)
        self._runs_experiment[run.run_id] = experiment_id
        self._benchmarks[run.run_id] = tuple(benchmark) if benchmark else None

    def get_request(self, run_id):
        try:
            return RunRequest.from_payload(self._requests[run_id])
        except KeyError:
            raise KeyError(run_id) from None

    def get_expected_names(self, run_id):
        return self._expected.get(run_id)

    def experiment_id(self, run_id):
        return self._runs_experiment.get(run_id)

    def benchmark_identity(self, run_id):
        """The pinned ``(content_hash, cases)``, or None when not recorded."""
        return self._benchmarks.get(run_id)

    def accepted_at(self, run_id):
        return self._accepted_at.get(run_id)

    def deadline_seconds(self, run_id):
        return self._deadlines.get(run_id)

    def get_intent(self, run_id, attempt=1):
        return self._intents.get((run_id, attempt))

    def put_intent(self, intent):
        self._intents[(intent.run_id, intent.attempt)] = intent
        return intent

    def all_intents(self):
        return list(self._intents.values())

    def runs_for(self, owner):
        return [run for run in self._runs.values() if run.owner == owner]

    def creation_record(self, user, key):
        return self._creation.get((user, key))

    def commit_experiment(self, user, key, fingerprint, instance):
        """One transaction: creation idempotency and the instance document.

        Returns the committed instance. A concurrent writer that lands the same
        key first wins: the same fingerprint returns that stored instance (an
        idempotent replay), a different one is a conflict. The caller's
        pre-read is only a fast path, never the guarantee.
        """
        self.commits += 1
        if (user, key) in self._creation:
            return self.replay_experiment(user, key, fingerprint)
        self._creation[(user, key)] = (fingerprint, instance.experiment_id)
        self._instances[instance.experiment_id] = instance
        return instance

    def replay_experiment(self, user, key, fingerprint):
        """The stored instance for a key, or Conflict when the body differs."""
        stored_fingerprint, experiment_id = self._creation[(user, key)]
        if stored_fingerprint != fingerprint:
            raise Conflict(f"idempotency key {key!r} was used for a different creation")
        return self._instances[experiment_id]

    def get_experiment(self, experiment_id):
        return self._instances.get(experiment_id)

    def all_experiments(self):
        return list(self._instances.values())

    def put_artifacts(self, run_id, entries):
        """Persist the verified, generation-pinned result metadata for a run."""
        self._artifacts[run_id] = tuple(entries)
        return self._artifacts[run_id]

    def get_artifacts(self, run_id):
        """The persisted result metadata, or () when the run has none yet."""
        return self._artifacts.get(run_id, ())


def firestore_repository(client=None, project=None, database=None):
    """Production Firestore adapter. Thin: every call maps to one document path.

    The client is injected (or built on first use) so tests never construct it and
    imports never read credentials at module load.
    """
    if client is None:
        from google.cloud import firestore  # imported lazily; not a test dependency

        client = firestore.Client(project=project, database=database)
    return FirestoreRepository(client)


class FirestoreRepository:
    """Firestore-backed repository: runs, requests, idempotency, intents, specs,
    created experiment instances and verified artifact metadata."""

    def __init__(self, client, transactional=None):
        self._client = client
        self._runs = client.collection("runs")
        self._requests = client.collection("requests")
        self._idempotency = client.collection("idempotency")
        self._intents = client.collection("enqueue_intents")
        self._specs = client.collection("batch_specs")
        self._experiments = client.collection("experiments")
        self._creation = client.collection("experiment_idempotency")
        self._artifacts = client.collection("run_artifacts")
        # `transactional` decorates the transaction callback; inject it so tests
        # never import a Google client.
        self._transactional = transactional

    def _decorate(self, callback):
        decorate = self._transactional
        if decorate is None:
            from google.cloud import firestore  # imported lazily

            decorate = firestore.transactional
        return decorate(callback)

    # --- mapping helpers -----------------------------------------------------
    @staticmethod
    def _run_from(document):
        from lifemate_cloud.run import Run, RunState

        return Run(
            run_id=document["run_id"],
            owner=document["owner"],
            request_fingerprint=document["request_fingerprint"],
            state=RunState(document.get("state", "QUEUED")),
            cancel_requested=bool(document.get("cancel_requested", False)),
            batch_phase=document.get("batch_phase"),
            failure_reason=document.get("failure_reason"),
        )

    @staticmethod
    def _run_to(run, accepted_at=None, deadline_seconds=None):
        return {
            "run_id": run.run_id,
            "owner": run.owner,
            "request_fingerprint": run.request_fingerprint,
            "state": run.state.value,
            "cancel_requested": run.cancel_requested,
            "batch_phase": run.batch_phase,
            "failure_reason": run.failure_reason,
            "accepted_at": accepted_at,
            "deadline_seconds": deadline_seconds,
        }

    @staticmethod
    def _instance_from(document):
        from lifemate_api.catalog import ExperimentInstance

        return ExperimentInstance(
            experiment_id=document["experiment_id"],
            template_id=document["template_id"],
            benchmark_id=document["benchmark_id"],
            dataset_id=document["dataset_id"],
            model_id=document["model_id"],
            label=document.get("label", ""),
            decoding=document.get("decoding", {}),
            mode=document["mode"],
            content_hash=document["content_hash"],
            created_by=document["created_by"],
            created_at=document["created_at"],
        )

    @staticmethod
    def _instance_to(instance):
        return {
            "experiment_id": instance.experiment_id,
            "template_id": instance.template_id,
            "benchmark_id": instance.benchmark_id,
            "dataset_id": instance.dataset_id,
            "model_id": instance.model_id,
            "label": instance.label,
            "decoding": instance.decoding,
            "mode": instance.mode,
            "content_hash": instance.content_hash,
            "created_by": instance.created_by,
            "created_at": instance.created_at,
        }

    def creation_record(self, user, key):
        snapshot = self._creation.document(idempotency_key(user, key)).get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict()
        return data["fingerprint"], data["experiment_id"]

    def get_experiment(self, experiment_id):
        snapshot = self._experiments.document(experiment_id).get()
        return self._instance_from(snapshot.to_dict()) if snapshot.exists else None

    def all_experiments(self):
        return [self._instance_from(doc.to_dict()) for doc in self._experiments.stream()]

    def put_artifacts(self, run_id, entries):
        """Persist verified, generation-pinned result metadata (identity only)."""
        self._artifacts.document(run_id).set({
            "run_id": run_id,
            "entries": [
                {"name": entry.name, "generation": int(entry.generation),
                 "checksum": entry.checksum, "size": getattr(entry, "size", None)}
                for entry in entries
            ],
        })
        return tuple(entries)

    def get_artifacts(self, run_id):
        """The persisted result metadata, or () when the run has none yet."""
        from lifemate_cloud.manifest import ManifestEntry

        snapshot = self._artifacts.document(run_id).get()
        if not snapshot.exists:
            return ()
        return tuple(
            ManifestEntry(name=row["name"], generation=int(row["generation"]),
                          checksum=row["checksum"], size=row.get("size"))
            for row in snapshot.to_dict().get("entries", ())
        )

    def commit_experiment(self, user, key, fingerprint, instance):
        """One transaction: creation idempotency and the instance document.

        Returns the committed instance. A concurrent writer holding the same key
        wins the transaction: the same fingerprint returns that stored instance
        (an idempotent replay), a different one is a conflict. The caller's
        pre-read is a fast path only; this check is the guarantee.
        """
        idempotency = self._creation.document(idempotency_key(user, key))
        document = self._experiments.document(instance.experiment_id)
        winner = {}

        @self._decorate
        def _commit(transaction):
            snapshot = idempotency.get(transaction=transaction)
            if snapshot.exists:
                data = snapshot.to_dict()
                if data["fingerprint"] != fingerprint:
                    raise Conflict(
                        f"idempotency key {key!r} was used for a different creation")
                stored = self._experiments.document(data["experiment_id"]).get(transaction=transaction)
                if not stored.exists:
                    raise KeyError(data["experiment_id"])
                winner["instance"] = self._instance_from(stored.to_dict())
                return
            transaction.set(idempotency, {
                "fingerprint": fingerprint,
                "experiment_id": instance.experiment_id,
            })
            transaction.set(document, self._instance_to(instance))
            winner["instance"] = instance

        _commit(self._client.transaction())
        return winner["instance"]

    # --- repository interface ------------------------------------------------
    def get_run(self, run_id):
        snapshot = self._runs.document(run_id).get()
        if not snapshot.exists:
            raise KeyError(run_id)
        return self._run_from(snapshot.to_dict())

    def put_run(self, run):
        document = self._runs.document(run.run_id).get()
        metadata = document.to_dict() if document.exists else {}
        self._runs.document(run.run_id).set(
            self._run_to(run, metadata.get("accepted_at"), metadata.get("deadline_seconds"))
        )
        return run

    def all_runs(self):
        return [self._run_from(doc.to_dict()) for doc in self._runs.stream()]

    def runs_for(self, owner):
        query = self._runs.where("owner", "==", owner).stream()
        return [self._run_from(doc.to_dict()) for doc in query]

    def accepted_at(self, run_id):
        snapshot = self._runs.document(run_id).get()
        return snapshot.to_dict().get("accepted_at") if snapshot.exists else None

    def deadline_seconds(self, run_id):
        snapshot = self._runs.document(run_id).get()
        return snapshot.to_dict().get("deadline_seconds") if snapshot.exists else None

    def get_request(self, run_id):
        snapshot = self._requests.document(run_id).get()
        if not snapshot.exists:
            raise KeyError(run_id)
        return RunRequest.from_payload(snapshot.to_dict()["payload"])

    def idempotency_record(self, user, key):
        snapshot = self._idempotency.document(idempotency_key(user, key)).get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict()
        return data["fingerprint"], data["run_id"]

    def get_expected_names(self, run_id):
        snapshot = self._requests.document(run_id).get()
        return tuple(snapshot.to_dict().get("expected_names", ())) if snapshot.exists else None

    def experiment_id(self, run_id):
        snapshot = self._requests.document(run_id).get()
        return snapshot.to_dict().get("experiment_id") if snapshot.exists else None

    def commit_acceptance(self, user, key, fingerprint, run, intent, request, accepted_at=None,
                          deadline_seconds=None, expected_names=(), experiment_id=None,
                          benchmark=None):
        idempotency = self._idempotency.document(idempotency_key(user, key))
        run_document = self._runs.document(run.run_id)
        request_document = self._requests.document(run.run_id)
        intent_document = self._intents.document(f"{run.run_id}:{intent.attempt}")

        @self._decorate
        def _commit(transaction):
            # Only Firestore writes here; no Cloud Tasks or other network call.
            snapshot = idempotency.get(transaction=transaction)
            if snapshot.exists:
                raise ValueError("acceptance committed twice for the same key")
            transaction.set(idempotency, {"fingerprint": fingerprint, "run_id": run.run_id})
            transaction.set(run_document, self._run_to(run, accepted_at, deadline_seconds))
            transaction.set(request_document, {
                "payload": request.payload(),
                "fingerprint": fingerprint,
                "expected_names": list(expected_names),
                "experiment_id": experiment_id,
                "benchmark_hash": benchmark[0] if benchmark else None,
                "benchmark_cases": benchmark[1] if benchmark else None,
            })
            transaction.set(intent_document, {
                "run_id": intent.run_id,
                "attempt": intent.attempt,
                "job_id": intent.job_id,
                "state": intent.state.value,
            })

        _commit(self._client.transaction())

    def benchmark_identity(self, run_id):
        """The pinned ``(content_hash, cases)``, or None when not recorded."""
        snapshot = self._requests.document(run_id).get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict()
        if data.get("benchmark_hash") is None:
            return None
        return data["benchmark_hash"], data.get("benchmark_cases")

    def get_intent(self, run_id, attempt=1):
        snapshot = self._intents.document(f"{run_id}:{attempt}").get()
        if not snapshot.exists:
            return None
        return self._intent_from(snapshot.to_dict())

    def put_intent(self, intent):
        self._intents.document(f"{intent.run_id}:{intent.attempt}").set({
            "run_id": intent.run_id,
            "attempt": intent.attempt,
            "job_id": intent.job_id,
            "state": intent.state.value,
        })
        return intent

    @staticmethod
    def _intent_from(data):
        from lifemate_api.acceptance import EnqueueIntent, IntentState

        return EnqueueIntent(
            run_id=data["run_id"],
            attempt=int(data["attempt"]),
            job_id=data["job_id"],
            state=IntentState(data["state"]),
        )

    def all_intents(self):
        return [self._intent_from(doc.to_dict()) for doc in self._intents.stream()]

    def get_batch_spec(self, run_id, attempt):
        snapshot = self._specs.document(f"{run_id}:{attempt}").get()
        if not snapshot.exists:
            return None
        return self._spec_from(snapshot.to_dict())

    def put_batch_spec(self, spec):
        self._specs.document(f"{spec.run_id}:{spec.attempt}").set({
            "job_id": spec.job_id,
            "request_id": spec.request_id,
            "run_id": spec.run_id,
            "attempt": spec.attempt,
            "request_fingerprint": spec.request_fingerprint,
            "retry_count": spec.retry_count,
        })
        return spec

    @staticmethod
    def _spec_from(data):
        from lifemate_cloud.batch import BatchJobSpec

        return BatchJobSpec(
            job_id=data["job_id"],
            request_id=data["request_id"],
            run_id=data["run_id"],
            attempt=int(data["attempt"]),
            request_fingerprint=data["request_fingerprint"],
            retry_count=int(data.get("retry_count", 0)),
        )

    def all_batch_specs(self):
        return [self._spec_from(doc.to_dict()) for doc in self._specs.stream()]
