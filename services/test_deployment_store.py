"""Durable dispatcher persistence and the approved Batch execution contract.

The production Firestore callbacks run against an SDK-faithful in-memory client.
Optional SDK contract tests also exercise real Firestore and Batch objects;
neither credentials nor network access are required.

The dispatcher is also built once through ``entry.build_service`` with fake
Firestore/Batch/Tasks clients and an environment derived from the reviewed
Terraform variables, so a rename on either side fails loudly here.
"""
import functools
import inspect
import pathlib
import re
import unittest

from lifemate_api.store import FirestoreRepository, InMemoryApiRepository
from lifemate_cloud.batch import BatchJobConfig, Mount
from lifemate_cloud.run import Run

from dispatcher import entry, google_adapters
from dispatcher.records import Admission, AdmissionSlot, RunOp, RunOpState
from dispatcher.service import DispatchPolicy, DispatchService
from dispatcher.store import DispatcherRepository, FirestoreDispatcherRepository, InMemoryManifestStore
from dispatcher.google_adapters import batch_config

REPO = pathlib.Path(__file__).resolve().parents[1]


class FakeDocument:
    def __init__(self, store, key):
        self._store = store
        self._key = key

    def get(self, transaction=None):
        if transaction is not None:
            transaction.document_reads.append(self._key)
        return FakeSnapshot(self._store.get(self._key))

    def set(self, data):
        self._store[self._key] = data


class FakeSnapshot:
    def __init__(self, data):
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return self._data


class FakeQuery:
    def __init__(self, docs, where=None):
        self._docs = docs
        self._where = where

    def where(self, field, op, value):
        return FakeQuery(self._docs, (field, value))

    def stream(self):
        rows = self._docs.values()
        if self._where:
            field, value = self._where
            rows = [row for row in rows if row.get(field) == value]
        return [FakeSnapshot(row) for row in rows]


class FakeCollection(FakeQuery):
    def document(self, key):
        return FakeDocument(self._docs, key)

    def add(self, data):
        self._docs[f"row-{len(self._docs)}"] = data


class FakeTransaction:
    def __init__(self):
        self.document_reads = []
        self._writes = []

    def get(self, document):
        # The SDK yields snapshots even when given one document reference.
        yield document.get(transaction=self)

    def set(self, document, data):
        self._writes.append((document, data))

    def commit(self):
        for document, data in self._writes:
            document.set(data)


class FakeFirestore:
    """Firestore documents and buffered transactions, without network calls."""

    def __init__(self):
        self._collections = {}
        self.transactions = []

    def collection(self, name):
        return FakeCollection(self._collections.setdefault(name, {}))

    def transaction(self):
        transaction = FakeTransaction()
        self.transactions.append(transaction)
        return transaction

    @staticmethod
    def transactional(callback):
        @functools.wraps(callback)
        def commit(transaction):
            result = callback(transaction)
            transaction.commit()
            return result

        return commit


class FakeRuns:
    """The API-owned repository the dispatcher shares."""

    def __init__(self):
        self.records = []

    def get_run(self, run_id):
        return self.records[-1]

    def put_run(self, run):
        self.records.append(run)
        return run

    def all_runs(self):
        return list(self.records)

    def get_request(self, run_id):
        return {"run_id": run_id}

    def get_expected_names(self, run_id):
        return ()

    def accepted_at(self, run_id):
        return None

    def deadline_seconds(self, run_id):
        return None

    def put_artifacts(self, run_id, entries):
        self.artifacts = (run_id, tuple(entries))

    def get_batch_spec(self, run_id, attempt):
        return None

    def put_batch_spec(self, spec):
        return spec

    def get_intent(self, run_id, attempt=1):
        return None

    def all_intents(self):
        return []

class FirestoreTransactionTests(unittest.TestCase):
    """Run production repository callbacks with the real SDK read contract."""

    def setUp(self):
        from lifemate_api.app import ApiSettings, create_app
        from test_api import AUDIENCE, NOW, ROLES, catalog, verifier

        self.client = FakeFirestore()
        self.api = FirestoreRepository(self.client, transactional=self.client.transactional)
        self.app = create_app(
            repository=self.api, verifier=verifier,
            settings=ApiSettings(iap_audience=AUDIENCE, roles=ROLES, catalog=catalog()),
            now=lambda: NOW,
        )

    def submit(self):
        from test_api import SUBMIT, call

        response = call(self.app, "POST", "/api/experiments/exp-1/runs",
                        key="run-key", body=SUBMIT)
        self.assertEqual(response.status, 202, response.json)
        return response.json["run_id"]

    def test_experiment_creation_and_replay_read_documents_in_transaction(self):
        from test_api import CREATE, call

        response = call(self.app, "POST", "/api/experiments", key="create-key", body=CREATE)
        self.assertEqual(response.status, 201, response.json)
        instance = self.api.get_experiment(response.json["experiment_id"])
        fingerprint, _ = self.api.creation_record(instance.created_by, "create-key")
        self.assertEqual(self.api.commit_experiment(
            instance.created_by, "create-key", fingerprint, instance), instance)
        self.assertEqual([len(tx.document_reads) for tx in self.client.transactions], [1, 2])

    def test_run_acceptance_reads_document_in_transaction(self):
        run_id = self.submit()
        self.assertEqual(self.api.get_run(run_id).state.value, "QUEUED")
        self.assertEqual(len(self.client.transactions[-1].document_reads), 1)

    def test_slot_claim_reads_document_in_transaction(self):
        from lifemate_cloud.batch import BatchJobSpec

        run_id = self.submit()
        repository = FirestoreDispatcherRepository(self.client, self.api)
        spec = BatchJobSpec.for_attempt(run_id, 1, self.api.get_run(run_id).request_fingerprint)
        record = RunOp(run_id=run_id, attempt=1, job_id=spec.job_id, request_id=spec.request_id)
        repository.claim_slot(run_id, 100, spec, record)
        self.assertEqual(self.client.transactions[-1].document_reads, ["singleton"])
        self.assertEqual(repository.get_op(run_id), record)

    def test_fake_transaction_get_returns_a_generator(self):
        snapshots = self.client.transaction().get(self.client.collection("runs").document("absent"))
        self.assertTrue(inspect.isgenerator(snapshots))
        self.assertFalse(next(snapshots).exists)

    def test_sdk_transaction_get_returns_a_generator(self):
        try:
            from google.auth.credentials import AnonymousCredentials
            from google.cloud import firestore
        except ImportError:
            self.skipTest("google-cloud-firestore is not installed")
        client = firestore.Client(project="test-project", credentials=AnonymousCredentials())
        snapshots = client.transaction().get(client.collection("runs").document("absent"))
        self.assertTrue(inspect.isgenerator(snapshots))
        snapshots.close()



def op(run_id="run-1"):
    return RunOp(run_id=run_id, attempt=1, job_id="lmr-abc", request_id="req-1")


class DurableDispatcherRepositoryTests(unittest.TestCase):

    def setUp(self):
        self.runs = FakeRuns()
        self.repository = FirestoreDispatcherRepository(FakeFirestore(), self.runs)

    def test_op_round_trips_every_field(self):
        self.repository.put_op(op())
        stored = self.repository.get_op("run-1")
        self.assertEqual(stored, op())
        self.assertEqual(self.repository.all_ops(), [op()])

    def test_missing_op_raises_key_error(self):
        with self.assertRaises(KeyError):
            self.repository.get_op("absent")

    def test_slot_starts_free_and_round_trips_reservations(self):
        self.assertTrue(self.repository.get_slot().is_free)
        slot = AdmissionSlot().claim("run-1", 500).request_release("verified")
        self.repository.put_slot(slot)
        stored = self.repository.get_slot()
        self.assertEqual(stored.reservation, Admission(run_id="run-1", cost=500))
        self.assertTrue(stored.release_verified)
        self.assertEqual(stored.evidence, "verified")

    def test_job_uid_index_is_durable(self):
        self.assertIsNone(self.repository.get_job_uid_index("lmr-abc"))
        self.repository.put_job_uid_index("lmr-abc", "uid-9")
        self.assertEqual(self.repository.get_job_uid_index("lmr-abc"), "uid-9")

    def test_audit_events_are_append_only_and_filterable(self):
        self.repository.audit("run-1", "accepted", {"cost": 1})
        self.repository.audit("run-2", "created")
        self.repository.audit("run-1", "created", {"uid": "u"})
        self.assertEqual(len(self.repository.events()), 3)
        self.assertEqual([row[1] for row in self.repository.events("run-1")], ["accepted", "created"])

    def test_shared_records_delegate_to_the_api_repository(self):
        sentinel = object()
        self.runs.records.append(sentinel)
        self.assertIs(self.repository.get_run("run-1"), sentinel)
        self.assertEqual(self.repository.all_runs(), [sentinel])

    def test_in_memory_repository_has_the_same_surface(self):
        memory = DispatcherRepository(self.runs)
        memory.put_op(op())
        memory.put_slot(AdmissionSlot().claim("run-1", 10))
        memory.put_job_uid_index("lmr-abc", "uid-9")
        memory.audit("run-1", "accepted")
        self.assertEqual(memory.get_op("run-1"), op())
        self.assertEqual(memory.get_job_uid_index("lmr-abc"), "uid-9")
        self.assertEqual(memory.get_slot().holder, "run-1")
        self.assertEqual(len(memory.events("run-1")), 1)


# Reviewed rendering of each ``dispatcher_env`` key. The *key set* comes from
# run.tf itself (``_terraform_env_block``), so this table only supplies values.
TERRAFORM_VALUES = {
    "PROJECT_ID": "test-project-123",
    "FIRESTORE_DATABASE": "(default)",
    "REGION": "asia-southeast1",
    "DISPATCH_URL": "https://dispatcher.example.run.app/internal/dispatch",
    "TASK_SERVICE_ACCOUNT": "sa-task-caller@p.iam.gserviceaccount.com",
    "DISPATCH_AUDIENCE": "https://dispatcher.example.run.app",
    "TASKS_LOCATION": "asia-southeast1",
    "TASKS_QUEUE": "lifemate-dispatch",
    "RESULTS_BUCKET": "example-private-123-results",
    "RESULT_PREFIX": "runs/",
    "BUDGET_CENTS": "1000",
    "DEADLINE_SECONDS": "1200",
    "BATCH_IMAGE": "asia-southeast1-docker.pkg.dev/p/lifemate-images/worker@sha256:" + "a" * 64,
    "BATCH_SERVICE_ACCOUNT": "sa-batch-worker@p.iam.gserviceaccount.com",
    "BATCH_MACHINE_TYPE": "g2-standard-4",
    "BATCH_BOOT_DISK_TYPE": "pd-balanced",
    "BATCH_BOOT_DISK_GB": "100",
    "TASK_TIMEOUT_SECONDS": "3600",
    "BATCH_MAX_RETRIES": "0",
    "BATCH_ARGUMENTS": "/mnt/results/manifest.json --launcher /mnt/app/launcher.py --pinned /mnt/app/pinned.json",
    "BATCH_MOUNTS": "bucket-data datasets /mnt/data ro;bucket-results results /mnt/results",
}


def _consumed_env_names(*functions):
    """Env names a function reads: ``env["X"]`` and ``env.get("X" ...)``.

    Source inspection lives only here, in the regression: production code keeps
    no runtime reflection. A rename in ``build_service``, ``batch_config`` or
    ``build_queue_client`` is picked up without a hand-kept list.
    """
    import ast
    import inspect

    names = set()
    for function in functions:
        tree = ast.parse(inspect.getsource(function))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
                    and node.value.id == "env"
                    and isinstance(node.slice, ast.Constant)
                    and isinstance(node.slice.value, str)):
                names.add(node.slice.value)
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "get"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "env" and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                names.add(node.args[0].value)
    return names


def _terraform_env_block(name):
    """Parse ``name = {`` ... ``}`` out of run.tf into a {KEY: value} map.

    Values are read as raw Terraform source, so expressions remain expressions;
    the tests only need the key set and a synthetic rendering of each value.
    """
    text = (REPO / "infra" / "terraform" / "dev" / "run.tf").read_text()
    body = re.search(rf"{name}\s*=\s*\{{(.*?)\n  \}}", text, re.S)
    if body is None:
        raise AssertionError(f"{name} block not found in run.tf")
    keys = {}
    for line in body.group(1).splitlines():
        match = re.match(r"\s*([A-Z][A-Z0-9_]*)\s*=\s*(.+?)\s*$", line)
        if match:
            keys[match.group(1)] = match.group(2)
    return keys


# Exactly the Terraform dispatcher env: same keys, no more and no fewer.
DEPLOY_ENVIRONMENT = {
    key: TERRAFORM_VALUES[key] for key in _terraform_env_block("dispatcher_env")
}
ENVIRONMENT = DEPLOY_ENVIRONMENT


class BatchConfigTests(unittest.TestCase):

    def test_config_renders_the_deployment_environment(self):
        config = batch_config(ENVIRONMENT)
        self.assertEqual(config.image, ENVIRONMENT["BATCH_IMAGE"])
        self.assertEqual(config.mounts[0], Mount("bucket-data", "datasets", "/mnt/data", ("ro",)))
        self.assertEqual(config.arguments[0], "/mnt/results/manifest.json")
        self.assertEqual(config.arguments[1:3], ("--launcher", "/mnt/app/launcher.py"))
        self.assertEqual(config.max_retry_count, 0)
        self.assertEqual(config.env("run-1", 2), {"RUN_ID": "run-1", "ATTEMPT": "2", "RESULT_PREFIX": "results/"})

    def test_mount_options_are_parsed(self):
        env = dict(ENVIRONMENT, BATCH_MOUNTS="bucket-data datasets /mnt/data ro,implicit-dirs")
        self.assertEqual(batch_config(env).mounts[0].options, ("ro", "implicit-dirs"))

    def test_malformed_mount_entry_is_rejected(self):
        with self.assertRaises(ValueError):
            batch_config(dict(ENVIRONMENT, BATCH_MOUNTS="bucket-data /mnt/data"))


    def test_unpinned_image_is_rejected(self):
        with self.assertRaises(ValueError):
            BatchJobConfig(image="worker:latest", service_account="sa@p.iam.gserviceaccount.com")

    def test_illegal_mount_is_rejected(self):
        with self.assertRaises(ValueError):
            Mount(bucket="", remote_path="", mount_path="/mnt/data")
        with self.assertRaises(ValueError):
            Mount(bucket="bucket-data", remote_path="datasets", mount_path="relative")

    def test_mounts_must_be_mount_records(self):
        with self.assertRaises(ValueError):
            BatchJobConfig(image="w@sha256:" + "a" * 64, service_account="sa@p.iam", mounts=("bucket",))

    def test_arguments_are_required_and_never_a_shell_command(self):
        env = dict(ENVIRONMENT)
        env.pop("BATCH_ARGUMENTS")
        with self.assertRaises(KeyError):
            batch_config(env)
        with self.assertRaises(ValueError):
            BatchJobConfig(image="w@sha256:" + "a" * 64, service_account="sa@p.iam")

    def test_worker_identity_is_not_the_task_caller(self):
        config = batch_config(ENVIRONMENT)
        self.assertEqual(config.service_account, ENVIRONMENT["BATCH_SERVICE_ACCOUNT"])
        self.assertNotEqual(config.service_account, ENVIRONMENT["TASK_SERVICE_ACCOUNT"])

    def test_terraform_dispatcher_env_matches_the_consumed_key_set(self):
        """The Terraform block MUST equal what the dispatcher actually reads.

        Consumed names are parsed here from the source of the functions that
        read ``env``; production code carries no such reflection. A rename on
        either side (e.g. back to ``BATCH_COMMAND``) fails loudly.
        """
        block = _terraform_env_block("dispatcher_env")
        self.assertEqual(block.get("BATCH_ARGUMENTS"), "var.batch_arguments")
        self.assertNotIn("BATCH_COMMAND", block)
        required = _consumed_env_names(
            entry.build_service,
            google_adapters.batch_config,
            google_adapters.build_queue_client,
        )
        self.assertEqual(set(block), required, "Terraform env and consumed set diverged")
        self.assertEqual(set(DEPLOY_ENVIRONMENT), set(block))  # synthetic env is exact


class _FakeApiRepositoryFactory:
    """Restores the API repository constructor around entry.build_service."""

    def __init__(self, repository):
        self._repository = repository

    def __call__(self, *args, **kwargs):
        return self._repository



class _FakeApiRepositoryFactory:
    """Stands in for the API's Firestore repository constructor."""

    def __init__(self, repository):
        self._repository = repository

    def __call__(self, *args, **kwargs):
        return self._repository


class _FakeRunsWithClient:
    """The API repository surface ``build_service`` needs at construction time."""

    def __init__(self, client):
        self._client = client


class BuildServiceTests(unittest.TestCase):
    """``entry.build_service`` wires real adapters from the reviewed env only.

    Only the *external* factories (Google clients, the Firestore repository
    constructor) are replaced. ``batch_config``, ``build_batch_client`` and the
    rest of the adapter wiring run for real, so a wrong or missing env key —
    including reverting to ``BATCH_COMMAND`` — fails here instead of in prod.
    """

    def setUp(self):
        self.calls = {}
        self._originals = {}
        self._patch(
            "lifemate_api.store.firestore_repository",
            _FakeApiRepositoryFactory(_FakeRunsWithClient(FakeFirestore())),
        )
        # The three seams that would reach the network are faked; everything
        # that only computes configuration stays real.
        self._patch(f"{google_adapters.__name__}.build_batch_client", self._recorder("build_batch_client"))
        self._patch(f"{google_adapters.__name__}.build_queue_client", self._recorder("build_queue_client"))
        self._patch(f"{google_adapters.__name__}.build_clock", self._recorder("build_clock"))
        self._patch(f"{google_adapters.__name__}.build_artifact_store", self._recorder("build_artifact_store"))
        self._patch(f"{google_adapters.__name__}.build_manifest_store", self._recorder("build_manifest_store"))

    def _patch(self, target, value):
        import importlib

        module, _, attribute = target.rpartition(".")
        owner = importlib.import_module(module)
        self._originals[target] = getattr(owner, attribute)
        setattr(owner, attribute, value)

    def tearDown(self):
        import importlib

        for target, original in self._originals.items():
            module, _, attribute = target.rpartition(".")
            setattr(importlib.import_module(module), attribute, original)

    def _recorder(self, name):
        def stub(*args, **kwargs):
            self.calls[name] = (args, kwargs)
            return f"<{name}>"

        return stub

    def test_build_service_consumes_the_terraform_key_set(self):
        service = entry.build_service(DEPLOY_ENVIRONMENT)
        self.assertIsNotNone(service)
        # Key set: exactly the parsed Terraform block, not a hand-kept list.
        self.assertEqual(set(DEPLOY_ENVIRONMENT), set(_terraform_env_block("dispatcher_env")))
        # The real batch_config rendered the approved contract from that env.
        batch_args, _ = self.calls["build_batch_client"]
        project, region, config = batch_args
        self.assertEqual(project, DEPLOY_ENVIRONMENT["PROJECT_ID"])
        self.assertEqual(region, DEPLOY_ENVIRONMENT["REGION"])
        self.assertEqual(config.image, DEPLOY_ENVIRONMENT["BATCH_IMAGE"])
        self.assertEqual(config.arguments[0], DEPLOY_ENVIRONMENT["BATCH_ARGUMENTS"].split()[0])
        self.assertEqual(config.service_account, DEPLOY_ENVIRONMENT["BATCH_SERVICE_ACCOUNT"])

    def test_missing_arguments_key_fails_like_the_old_batch_command_bug(self):
        env = {key: value for key, value in DEPLOY_ENVIRONMENT.items() if key != "BATCH_ARGUMENTS"}
        with self.assertRaises(KeyError):
            entry.build_service(env)

    def test_build_service_treats_an_empty_env_as_authoritative(self):
        # Mirrors app.py/server.py: an explicitly empty env is used as-is, so
        # os.environ is never silently merged in to mask a missing key.
        with self.assertRaises(KeyError):
            entry.build_service({})


class _StubBatch:
    """Batch seam: records creates, answers reads, cancels to a terminal record."""

    def __init__(self):
        self.jobs = {}

    def create_job(self, job_id, request_id, spec):
        self.jobs[job_id] = {"uid": f"uid-{job_id}", "request_id": request_id,
                             "state": "ACTIVE", "phase": "RUNNING"}
        return self.jobs[job_id]["uid"]

    def get_job(self, job_id):
        return dict(self.jobs[job_id]) if job_id in self.jobs else None

    def cancel_job(self, job_id):
        job = self.jobs.get(job_id)
        if job is None:
            return None
        job.update(state="CANCELLED", phase="CANCELLED")
        return dict(job)


class _StubQueue:
    def __init__(self):
        self.sent = []

    def enqueue_dispatch(self, run_id):
        self.sent.append(run_id)
        return run_id


class _StubClock:
    def __init__(self, now):
        self.value = now

    def now(self):
        return self.value


class ApiLifecycleTests(unittest.TestCase):
    """Deadline and success run over the real API store + dispatcher repository."""

    NAMES = ("result/a.json", "result/b.json")

    def setUp(self):
        from lifemate_cloud.artifacts import InMemoryArtifactStore
        from lifemate_cloud.requests import RunRequest

        self.api = InMemoryApiRepository()
        self.repository = DispatcherRepository(self.api)
        self.artifacts = InMemoryArtifactStore()
        self.manifests = InMemoryManifestStore()
        self.batch = _StubBatch()
        self.queue = _StubQueue()
        self.clock = _StubClock(now=1_000.0)
        self.request = RunRequest(
            dataset_id="ds", dataset_hash="a" * 64, model_id="m", model_hash="b" * 64,
            mode="agent", decoding={}, benchmark_id="b", machine_type="g2-standard-4",
            region="asia-southeast1", timeout_seconds=60, retry_allowance=0,
            source_sha="c" * 40, image_digest="sha256:" + "d" * 64, inputs={},
        )
        intent = type("Intent", (), {"run_id": "run-1", "attempt": 1})()
        self.run = Run(run_id="run-1", owner="alice",
                       request_fingerprint=self.request.fingerprint())
        # Acceptance goes through the real API transaction: the records the
        # dispatcher reads are the API's, not the test's.
        self.api.commit_acceptance(
            "alice", "key-1", self.run.request_fingerprint, self.run, intent, self.request,
            accepted_at=self.clock.now(), deadline_seconds=100,
            expected_names=self.NAMES,
        )

    def _service(self):
        service = DispatchService(
            self.repository,
            self.batch,
            self.queue,
            self.clock,
            self.artifacts,
            manifests=self.manifests,
            policy=DispatchPolicy(budget=10_000, deadline_seconds=3_600),
        )
        service.accept(self.run.run_id, 100)
        service.dispatch(self.run.run_id)
        return service

    def test_deadline_is_enforced_from_the_api_accepted_record(self):
        service = self._service()
        # 100s deadline was recorded by the API; the 3600s policy is ignored.
        self.clock.value = 1_000.0 + 101
        op = service.enforce_deadline(self.run.run_id)
        self.assertEqual(op.state, RunOpState.CANCELED)
        self.assertTrue(self.repository.get_slot().is_free)

    def test_deadline_holds_before_the_api_record_expires(self):
        service = self._service()
        self.clock.value = 1_000.0 + 99  # under the API's 100s, under the policy too
        op = service.enforce_deadline(self.run.run_id)
        self.assertNotEqual(op.state, RunOpState.CANCELED)

    def test_success_finalizes_from_api_expected_names_and_a_verified_manifest(self):
        from lifemate_cloud.manifest import ManifestEntry, ResultManifest

        service = self._service()
        job_id = self.repository.get_op(self.run.run_id).job_id
        self.batch.jobs[job_id].update(state="SUCCEEDED", phase="SUCCEEDED")
        document = ResultManifest.create(self.run.run_id, self.NAMES)
        for name in self.NAMES:
            self.artifacts.put_if_absent(name, b"payload")
            head = self.artifacts.head(name)
            document = document.add(
                ManifestEntry(name=name, generation=head.generation,
                              checksum=head.checksum, size=len(head.content))
            )
        self.manifests.put(document)
        op = service.reconcile(self.run.run_id)
        self.assertEqual(op.state, RunOpState.SUCCEEDED)
        self.assertTrue(op.manifest_verified)
        self.assertTrue(self.repository.get_slot().is_free)
        # Verified identity is published for the API/dashboard read-back.
        stored = self.api.get_artifacts(self.run.run_id)
        self.assertEqual({entry.name for entry in stored}, set(self.NAMES))
        self.assertTrue(all(entry.generation >= 1 for entry in stored))

    def test_manifest_outside_api_expected_names_never_succeeds(self):
        from lifemate_cloud.manifest import ManifestEntry, ResultManifest

        service = self._service()
        job_id = self.repository.get_op(self.run.run_id).job_id
        self.batch.jobs[job_id].update(state="SUCCEEDED", phase="SUCCEEDED")
        document = ResultManifest.create(self.run.run_id, ("result/other.json",))
        self.artifacts.put_if_absent("result/other.json", b"payload")
        head = self.artifacts.head("result/other.json")
        document = document.add(
            ManifestEntry(name="result/other.json", generation=head.generation,
                          checksum=head.checksum, size=len(head.content))
        )
        self.manifests.put(document)
        op = service.reconcile(self.run.run_id)
        self.assertEqual(op.state, RunOpState.FAILED)
        self.assertEqual(self.repository.get_slot().holder, self.run.run_id)
        # Unverified or conflicting artifacts publish no metadata.
        self.assertEqual(self.api.get_artifacts(self.run.run_id), ())

    def test_checksum_mismatch_publishes_no_artifact_metadata(self):
        from lifemate_cloud.manifest import ManifestEntry, ResultManifest

        service = self._service()
        job_id = self.repository.get_op(self.run.run_id).job_id
        self.batch.jobs[job_id].update(state="SUCCEEDED", phase="SUCCEEDED")
        document = ResultManifest.create(self.run.run_id, self.NAMES)
        for name in self.NAMES:
            self.artifacts.put_if_absent(name, b"payload")
            head = self.artifacts.head(name)
            checksum = "0" * 64  # valid shape, wrong bytes
            document = document.add(
                ManifestEntry(name=name, generation=head.generation,
                              checksum=checksum, size=len(head.content))
            )
        self.manifests.put(document)
        op = service.reconcile(self.run.run_id)
        self.assertEqual(op.state, RunOpState.FAILED)
        self.assertEqual(self.api.get_artifacts(self.run.run_id), ())
        self.assertEqual(self.repository.get_slot().holder, self.run.run_id)

    def test_claim_slot_is_all_or_nothing_with_an_unwritable_spec(self):
        from lifemate_cloud.batch import BatchJobSpec
        from lifemate_cloud.errors import Conflict

        class FrozenSpecs(InMemoryApiRepository):
            def put_batch_spec(self, spec):
                raise RuntimeError("spec write failed")

        runs = FrozenSpecs()
        repository = DispatcherRepository(runs)
        repository.put_run(self.run)
        spec = BatchJobSpec.for_attempt(self.run.run_id, 1, self.run.request_fingerprint)
        with self.assertRaises(RuntimeError):
            repository.claim_slot(self.run.run_id, 100, spec,
                                  RunOp(run_id=self.run.run_id, attempt=1, job_id=spec.job_id,
                                        request_id=spec.request_id))
        self.assertTrue(repository.get_slot().is_free)
        self.assertEqual(repository.all_ops(), [])

    def test_two_claims_on_the_real_store_admit_one(self):
        from lifemate_cloud.batch import BatchJobSpec
        from lifemate_cloud.errors import Conflict

        spec = BatchJobSpec.for_attempt(self.run.run_id, 1, self.run.request_fingerprint)
        record = RunOp(run_id=self.run.run_id, attempt=1, job_id=spec.job_id,
                       request_id=spec.request_id)
        self.repository.claim_slot(self.run.run_id, 100, spec, record)
        with self.assertRaises(Conflict):
            self.repository.claim_slot(self.run.run_id, 100, spec, record)
        self.assertEqual(self.repository.all_ops(), [record])
        self.assertEqual(self.api.get_batch_spec(self.run.run_id, 1), spec)

    def test_sweep_repairs_an_api_accepted_run_with_a_lost_task(self):
        """Acceptance stops before the task: the sweep admits and re-issues it."""
        service = DispatchService(
            self.repository, self.batch, self.queue, self.clock, self.artifacts,
            manifests=self.manifests, policy=DispatchPolicy(budget=10_000),
        )
        self.assertEqual(self.repository.all_ops(), [])
        results = service.sweep()
        self.assertEqual(results, {self.run.run_id: RunOpState.ACTIVE.value})
        self.assertEqual(self.queue.sent[-1], self.run.run_id)
        self.assertEqual(self.repository.get_slot().holder, self.run.run_id)


class BatchProtoShapeTests(unittest.TestCase):
    """The CreateJob payload must match the installed ``google-cloud-batch``.

    Nothing else exercised this translation, and both defects found here were
    silent: a nonexistent ``Volume.GCS`` mount and an output-only ``uid`` that
    is never accepted as a constructor argument. No network or credentials are
    used; only proto construction.
    """

    def setUp(self):
        try:
            from google.cloud import batch_v1
        except ImportError:  # optional dependency, absent from the stdlib-only env
            self.skipTest("google-cloud-batch is not installed")
        self.batch_v1 = batch_v1
        self.config = batch_config(dict(ENVIRONMENT, BATCH_MOUNTS="bucket-data datasets /mnt/data ro"))
        # Anonymous credentials: the real client, no ADC lookup, no network.
        from google.auth.credentials import AnonymousCredentials

        self.api = google_adapters.build_batch_client(
            "p", "asia-southeast1", self.config,
            client=batch_v1.BatchServiceClient(
                credentials=AnonymousCredentials(),
                client_options={"api_endpoint": "asia-southeast1-batch.googleapis.com"},
            ))

    def _payload(self):
        from lifemate_cloud.batch import BatchJobSpec

        spec = BatchJobSpec.for_attempt("run-1", 1, "f" * 64)
        return spec, self.api.job_for(spec.job_id, spec.request_id, spec)

    def test_gcs_volume_carries_the_bucket_path_and_mount_point(self):
        _, job = self._payload()
        volume = job.task_groups[0].task_spec.volumes[0]
        self.assertEqual(volume.gcs.remote_path, "bucket-data/datasets")
        self.assertEqual(volume.mount_path, "/mnt/data")
        self.assertEqual(list(volume.mount_options), ["ro"])

    def test_job_payload_leaves_output_only_fields_unset(self):
        # A constructor that receives ``uid`` would raise in the real client.
        _, job = self._payload()
        self.assertEqual(job.uid, "")
        self.assertEqual(job.name, "")


    def test_create_returns_name_and_uid_from_the_real_response(self):
        from lifemate_cloud.batch import BatchJobSpec
        spec = BatchJobSpec.for_attempt("run-1", 1, "f" * 64)
        created = self.batch_v1.Job()
        created.name = "projects/p/locations/r/jobs/" + spec.job_id
        created.uid = "uid-123"

        class Client:
            def create_job(self, request):
                self.request = request
                return created

        self.api._client = Client()
        name, uid = self.api.create_job(spec.job_id, spec.request_id, spec)
        self.assertEqual((name, uid), (created.name, "uid-123"))
        self.assertEqual(self.api._client.request.job_id, spec.job_id)


if __name__ == "__main__":
    unittest.main()
