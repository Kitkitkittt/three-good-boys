"""Durable acceptance: what the dispatcher later reads must be pinned server data."""
import unittest

from lifemate_api.acceptance import AcceptanceService, EnqueueIntent, IntentState
from lifemate_api.store import FirestoreRepository, InMemoryApiRepository, idempotency_key
from lifemate_cloud.errors import Conflict
from lifemate_cloud.requests import RunRequest
from lifemate_cloud.roles import Role
from lifemate_cloud.run import RunState


def request(**overrides):
    fields = dict(
        dataset_id="ds-1",
        dataset_hash="a" * 64,
        model_id="mdl-1",
        model_hash="b" * 64,
        mode="agent",
        decoding={"temperature": 0.0},
        benchmark_id="public-test",
        machine_type="g2-standard-8",
        region="asia-southeast1",
        timeout_seconds=1800,
        retry_allowance=0,
        source_sha="c" * 40,
        image_digest="sha256:" + "d" * 64,
        inputs={"models/mdl-1.bin": 1},
    )
    fields.update(overrides)
    return RunRequest(**fields)


def service():
    return AcceptanceService(InMemoryApiRepository(), new_run_id=lambda: "run-1")


class PinnedAcceptanceTests(unittest.TestCase):
    def accept(self, **kwargs):
        return service().accept(
            "alice", Role.RESEARCHER, "k1", request(),
            expected_names=("predictions.jsonl", "summary.json"),
            deadline_seconds=7200, accepted_at="2026-10-30T12:00:00+00:00", **kwargs,
        )

    def test_the_canonical_request_is_pinned_on_the_run(self):
        runs = AcceptanceService(InMemoryApiRepository(), new_run_id=lambda: "run-1")
        run = runs.accept("alice", Role.RESEARCHER, "k1", request(), expected_names=("p.jsonl",))
        self.assertEqual(runs.request_for(run.run_id), request())

    def test_coverage_deadline_and_accept_time_are_persisted(self):
        repository = InMemoryApiRepository()
        runs = AcceptanceService(repository, new_run_id=lambda: "run-1")
        run = runs.accept("alice", Role.RESEARCHER, "k1", request(),
                          expected_names=("p.jsonl", "s.json"), deadline_seconds=7200,
                          accepted_at="2026-10-30T12:00:00+00:00")
        self.assertEqual(repository.get_expected_names(run.run_id), ("p.jsonl", "s.json"))
        self.assertEqual(repository.deadline_seconds(run.run_id), 7200)
        self.assertEqual(repository.accepted_at(run.run_id), "2026-10-30T12:00:00+00:00")

    def test_the_intent_is_persisted_pending_before_any_enqueue(self):
        repository = InMemoryApiRepository()
        runs = AcceptanceService(repository, new_run_id=lambda: "run-1")
        run = runs.accept("alice", Role.RESEARCHER, "k1", request())
        intent = repository.get_intent(run.run_id)
        self.assertEqual(intent.state, IntentState.PENDING)
        self.assertEqual(intent.job_id, EnqueueIntent.for_run(run.run_id, request().fingerprint()).job_id)

    def test_idempotent_replay_does_not_write_again(self):
        repository = InMemoryApiRepository()
        runs = AcceptanceService(repository, new_run_id=lambda: "run-1")
        first = runs.accept("alice", Role.RESEARCHER, "k1", request())
        second = runs.accept("alice", Role.RESEARCHER, "k1", request())
        self.assertEqual(first.run_id, second.run_id)
        self.assertEqual(repository.commits, 1)

    def test_conflicting_replay_is_refused(self):
        runs = AcceptanceService(InMemoryApiRepository(), new_run_id=lambda: "run-1")
        runs.accept("alice", Role.RESEARCHER, "k1", request())
        with self.assertRaises(Conflict):
            runs.accept("alice", Role.RESEARCHER, "k1", request(region="us-central1"))

    def test_read_only_surfaces_the_dispatcher_uses(self):
        repository = InMemoryApiRepository()
        runs = AcceptanceService(repository, new_run_id=lambda: "run-1")
        run = runs.accept("alice", Role.RESEARCHER, "k1", request())
        self.assertEqual(repository.get_run(run.run_id).state, RunState.QUEUED)
        self.assertEqual(repository.get_request(run.run_id), request())
        self.assertIsNotNone(repository.get_intent(run.run_id))
        self.assertEqual(len(repository.all_intents()), 1)

    def test_idempotency_document_key_is_user_scoped_hash(self):
        self.assertNotEqual(idempotency_key("alice", "k1"), idempotency_key("bob", "k1"))
        self.assertRegex(idempotency_key("alice", "k1"), r"^[0-9a-f]{64}$")


    def test_artifacts_start_empty_and_round_trip(self):
        from lifemate_cloud.manifest import ManifestEntry

        repository = InMemoryApiRepository()
        self.assertEqual(repository.get_artifacts("run-1"), ())
        entry = ManifestEntry(name="predictions.jsonl", generation=5, checksum="a" * 64)
        repository.put_artifacts("run-1", (entry,))
        self.assertEqual(repository.get_artifacts("run-1"), (entry,))
        self.assertEqual(repository.get_artifacts("run-2"), ())

class FirestoreAdapterTests(unittest.TestCase):
    """The adapter's transaction callback is exercised without a real client."""

    class _Snapshot:
        def __init__(self, data=None):
            self.exists = data is not None
            self._data = data or {}

        def to_dict(self):
            return dict(self._data)

    class _Document:
        def __init__(self, store, path):
            self._store = store
            self._path = path

        def get(self, transaction=None):
            return FirestoreAdapterTests._Snapshot(self._store.get(self._path))

        def set(self, data):
            self._store[self._path] = data

    class _Collection:
        def __init__(self, store, name):
            self._store = store
            self._name = name

        def document(self, key):
            return FirestoreAdapterTests._Document(self._store, f"{self._name}/{key}")

        def stream(self):
            prefix = f"{self._name}/"
            return [FirestoreAdapterTests._Snapshot(value) for key, value in self._store.items()
                    if key.startswith(prefix)]

    class _Transaction:
        def __init__(self, store):
            self._store = store

        def get(self, document):
            yield document.get(transaction=self)

        def set(self, document, data):
            document.set(data)

    class _Client:
        def __init__(self):
            self.store = {}
            self.writes = 0

        def collection(self, name):
            return FirestoreAdapterTests._Collection(self.store, name)

        def transaction(self):
            return FirestoreAdapterTests._Transaction(self.store)

    @staticmethod
    def _transactional(callback):
        def run(transaction):
            return callback(transaction)

        return run

    def repository(self):
        self.client = self._Client()
        return FirestoreRepository(self.client, transactional=self._transactional)

    def test_acceptance_writes_run_request_intent_and_idempotency(self):
        from lifemate_api.acceptance import EnqueueIntent
        from lifemate_cloud.run import Run

        repository = self.repository()
        run = Run(run_id="run-1", owner="alice", request_fingerprint=request().fingerprint())
        intent = EnqueueIntent.for_run("run-1", request().fingerprint())
        repository.commit_acceptance(
            "alice", "k1", request().fingerprint(), run, intent, request(),
            accepted_at="2026-10-30T12:00:00+00:00", deadline_seconds=7200,
            expected_names=("p.jsonl",),
        )
        self.assertEqual(repository.get_run("run-1"), run)
        self.assertEqual(repository.get_request("run-1"), request())
        self.assertEqual(repository.get_intent("run-1").state, IntentState.PENDING)
        self.assertEqual(repository.get_expected_names("run-1"), ("p.jsonl",))
        self.assertEqual(repository.accepted_at("run-1"), "2026-10-30T12:00:00+00:00")
        self.assertEqual(repository.deadline_seconds("run-1"), 7200)
        self.assertEqual(repository.idempotency_record("alice", "k1")[1], "run-1")

    def test_put_run_preserves_acceptance_metadata(self):
        from lifemate_cloud.run import Run, RunState

        repository = self.repository()
        run = Run(run_id="run-1", owner="alice", request_fingerprint="f" * 64)
        self.client.store["runs/run-1"] = {
            "run_id": "run-1", "owner": "alice", "request_fingerprint": "f" * 64,
            "state": "QUEUED", "cancel_requested": False, "batch_phase": None,
            "failure_reason": None, "accepted_at": "then", "deadline_seconds": 60,
        }
        repository.put_run(run.transition(RunState.SUBMITTING))
        self.assertEqual(repository.accepted_at("run-1"), "then")
        self.assertEqual(repository.deadline_seconds("run-1"), 60)

    def test_experiment_creation_writes_instance_and_idempotency(self):
        repository = self.repository()
        created = instance()
        repository.commit_experiment("alice", "c1", "f" * 64, created)
        self.assertEqual(repository.get_experiment(created.experiment_id), created)
        self.assertEqual(repository.creation_record("alice", "c1"),
                         ("f" * 64, created.experiment_id))
        self.assertEqual(repository.creation_record("bob", "c1"), None)
        self.assertEqual(len(repository.all_experiments()), 1)

    def test_commit_returns_the_stored_instance_for_a_replayed_key(self):
        repository = self.repository()
        created = instance()
        self.assertIs(repository.commit_experiment("alice", "c1", "f" * 64, created), created)
        # A concurrent writer holding the same key and body gets the winner back.
        won = repository.commit_experiment("alice", "c1", "f" * 64, instance("exp-2"))
        self.assertEqual(won, created)
        self.assertEqual(len(repository.all_experiments()), 1)

    def test_commit_conflicts_on_a_replayed_key_with_a_different_body(self):
        repository = self.repository()
        repository.commit_experiment("alice", "c1", "f" * 64, instance())
        with self.assertRaises(Conflict):
            repository.commit_experiment("alice", "c1", "e" * 64, instance("exp-2"))
        self.assertEqual(len(repository.all_experiments()), 1)

    def test_artifacts_round_trip_through_firestore_as_manifest_entries(self):
        from lifemate_cloud.manifest import ManifestEntry

        repository = self.repository()
        entries = (ManifestEntry(name="predictions.jsonl", generation=9,
                                 checksum="e" * 64, size=512),
                   ManifestEntry(name="report.json", generation=2, checksum="f" * 64))
        repository.put_artifacts("run-1", entries)
        self.assertEqual(repository.get_artifacts("run-1"), entries)
        self.assertEqual(repository.get_artifacts("run-absent"), ())

    def test_artifacts_are_stored_as_identity_only(self):
        from lifemate_cloud.manifest import ManifestEntry

        repository = self.repository()
        repository.put_artifacts("run-1", (ManifestEntry(name="a.jsonl", generation=3,
                                                        checksum="a" * 64),))
        stored = self.client.store["run_artifacts/run-1"]
        self.assertEqual(stored["entries"],
                         [{"name": "a.jsonl", "generation": 3, "checksum": "a" * 64,
                           "size": None}])


def instance(experiment_id="exp-1"):
    from lifemate_api.catalog import ExperimentInstance

    return ExperimentInstance(
        experiment_id=experiment_id, template_id="tpl-1", benchmark_id="bench-1",
        dataset_id="ds-1", model_id="mdl-1", label="Compare", decoding={}, mode="agent",
        content_hash="c" * 64, created_by="alice", created_at="2026-10-30T12:00:00+00:00",
    )


class ExperimentServiceTests(unittest.TestCase):
    """Creation is durable, user-scoped and idempotent exactly like acceptance."""

    def setUp(self):
        from lifemate_api.catalog import Artifact, Experiment
        from lifemate_api.experiments import ExperimentService

        self.repository = InMemoryApiRepository()
        self.service = ExperimentService(
            repository=self.repository, new_experiment_id=lambda: "exp-1")
        self.template = Experiment(id="tpl-1", label="Compare", benchmark_id="bench-1",
                                   cases=12, content_hash="c" * 64, mode="agent",
                                   decoding={"temperature": 0.0})
        self.dataset = Artifact(id="ds-1", label="D", hash="a" * 64, objects={})
        self.model = Artifact(id="mdl-1", label="M", hash="b" * 64, objects={})

    def create(self, user="alice", key="c1", role=Role.RESEARCHER, label="Mine"):
        return self.service.create(user, role, key, self.template, self.dataset, self.model,
                                   label, "2026-10-30T12:00:00+00:00")

    def test_creation_persists_a_real_instance_from_the_template(self):
        created = self.create()
        self.assertEqual(self.repository.get_experiment(created.experiment_id), created)
        self.assertEqual(created.template_id, "tpl-1")
        self.assertEqual(created.benchmark_id, "bench-1")
        self.assertEqual(created.dataset_id, "ds-1")
        self.assertEqual(created.model_id, "mdl-1")
        self.assertEqual(created.label, "Mine")
        self.assertEqual(created.created_by, "alice")
        self.assertEqual(self.repository.commits, 1)

    def test_replay_returns_the_stored_instance_without_a_second_write(self):
        first = self.create()
        second = self.create()
        self.assertEqual(first.experiment_id, second.experiment_id)
        self.assertEqual(self.repository.commits, 1)

    def test_a_different_body_conflicts(self):
        self.create()
        with self.assertRaises(Conflict):
            self.create(label="Other")
        self.assertEqual(self.repository.commits, 1)

    def test_the_create_key_is_user_scoped(self):
        self.create(user="alice")
        self.create(user="bob")
        self.assertEqual(self.repository.commits, 2)

    def test_a_concurrent_winner_is_returned_instead_of_failing(self):
        """The pre-read misses, then another writer commits the same key.

        The commit must resolve inside the transaction, not trust the earlier
        read: the same body returns the winner, a different body conflicts.
        """
        from lifemate_api.experiments import creation_fingerprint

        winner = instance(experiment_id="exp-winner")
        same = creation_fingerprint("alice", "tpl-1", "ds-1", "mdl-1", "Mine")

        def miss_then_differing_body():
            def read(_user, _key):
                # Another writer lands between this read and this commit.
                self.repository._creation[("alice", "c1")] = ("e" * 64, "exp-winner")
                self.repository._instances["exp-winner"] = winner
                return None
            return read

        self.repository.creation_record = miss_then_differing_body()
        with self.assertRaises(Conflict):
            self.create()
        self.assertEqual(self.repository.get_experiment("exp-winner"), winner)

        def miss_then_same_body(_user, _key):
            self.repository._creation[("alice", "c1")] = (same, "exp-winner")
            return None

        self.repository.creation_record = miss_then_same_body
        self.assertIs(self.create(), winner)

    def test_creation_requires_submit_rights_and_a_key(self):
        with self.assertRaises(Exception):
            self.create(role=Role.VIEWER)
        self.assertEqual(self.repository.commits, 0)
        with self.assertRaises(ValueError):
            self.create(key="  ")
        self.assertEqual(self.repository.commits, 0)


if __name__ == "__main__":
    unittest.main()
