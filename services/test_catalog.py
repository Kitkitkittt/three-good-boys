"""Server-side resolution: the client names approved ids, the server pins the rest."""
import unittest

from lifemate_api.catalog import Artifact, Catalog, Experiment, UnknownArtifact

DATASET = Artifact(id="ds-1", label="Public test", hash="a" * 64,
                   objects={"datasets/ds-1.jsonl": 99})
MODEL = Artifact(id="mdl-1", label="Baseline", hash="b" * 64,
                 objects={"models/mdl-1.bin": 12345})
EXPERIMENT = Experiment(id="exp-1", label="Compare", benchmark_id="public-test", cases=12,
                        content_hash="c" * 64, mode="agent", decoding={"temperature": 0.0})


def catalog():
    return Catalog(
        datasets={"ds-1": DATASET},
        models={"mdl-1": MODEL},
        experiments={"exp-1": EXPERIMENT},
        machine_type="g2-standard-8",
        region="asia-southeast1",
        timeout_seconds=1800,
        retry_allowance=0,
        source_sha="d" * 40,
        image_digest="sha256:" + "e" * 64,
        decoding_defaults={"top_p": 1.0},
    )


class ResolutionTests(unittest.TestCase):
    def resolve(self, body):
        return catalog().resolve("exp-1", body)

    def test_policy_fields_come_from_the_server(self):
        request = self.resolve({"dataset_id": "ds-1", "model_id": "mdl-1", "decoding": {}})
        self.assertEqual(request.machine_type, "g2-standard-8")
        self.assertEqual(request.region, "asia-southeast1")
        self.assertEqual(request.timeout_seconds, 1800)
        self.assertEqual(request.retry_allowance, 0)
        self.assertEqual(request.image_digest, "sha256:" + "e" * 64)
        self.assertEqual(request.source_sha, "d" * 40)

    def test_hashes_and_object_generations_come_from_the_registry(self):
        request = self.resolve({"dataset_id": "ds-1", "model_id": "mdl-1", "decoding": {}})
        self.assertEqual(request.dataset_hash, "a" * 64)
        self.assertEqual(request.model_hash, "b" * 64)
        self.assertEqual(request.inputs, {"datasets/ds-1.jsonl": 99, "models/mdl-1.bin": 12345})

    def test_client_decoding_overrides_server_defaults(self):
        request = self.resolve({"dataset_id": "ds-1", "model_id": "mdl-1",
                                "decoding": {"top_p": 0.5}})
        self.assertEqual(request.decoding, {"temperature": 0.0, "top_p": 0.5})

    def test_unknown_client_field_is_refused(self):
        for field in ("machine_type", "region", "image_digest", "timeout_seconds", "inputs"):
            with self.assertRaises(UnknownArtifact, msg=field):
                self.resolve({"dataset_id": "ds-1", "model_id": "mdl-1", "decoding": {}, field: "x"})

    def test_missing_client_field_is_refused(self):
        with self.assertRaises(UnknownArtifact):
            self.resolve({"dataset_id": "ds-1", "decoding": {}})

    def test_unknown_ids_are_refused(self):
        with self.assertRaises(UnknownArtifact):
            self.resolve({"dataset_id": "ds-9", "model_id": "mdl-1", "decoding": {}})
        with self.assertRaises(UnknownArtifact):
            self.resolve({"dataset_id": "ds-1", "model_id": "mdl-9", "decoding": {}})

    def test_unknown_experiment_is_refused(self):
        with self.assertRaises(UnknownArtifact):
            catalog().resolve("exp-9", {"dataset_id": "ds-1", "model_id": "mdl-1", "decoding": {}})

    def test_the_dashboard_body_is_accepted(self):
        # Ticket 18 sends exactly these keys, including the echoed experiment id.
        request = catalog().resolve("exp-1", {
            "dataset_id": "ds-1", "model_id": "mdl-1", "experiment_id": "exp-1", "decoding": {},
        })
        self.assertEqual(request.dataset_id, "ds-1")

    def test_a_mismatched_echoed_experiment_is_refused(self):
        with self.assertRaises(UnknownArtifact):
            catalog().resolve("exp-1", {"dataset_id": "ds-1", "model_id": "mdl-1",
                                        "experiment_id": "exp-9", "decoding": {}})

    def test_decoding_is_optional(self):
        request = catalog().resolve("exp-1", {"dataset_id": "ds-1", "model_id": "mdl-1"})
        self.assertEqual(request.decoding, {"temperature": 0.0, "top_p": 1.0})

    def test_resolve_pins_the_registry_identity_on_the_canonical_request(self):
        request = self.resolve({"dataset_id": "ds-1", "model_id": "mdl-1"})
        self.assertEqual(request.benchmark_id, "public-test")
        self.assertEqual(request.dataset_id, "ds-1")
        self.assertEqual(request.dataset_hash, "a" * 64)
        self.assertEqual(request.model_id, "mdl-1")
        self.assertEqual(request.model_hash, "b" * 64)

    def test_approved_lists_templates_without_hiding_datasets_or_models(self):
        approved = catalog().approved()
        self.assertEqual(approved["datasets"], [{"id": "ds-1", "label": "Public test"}])
        self.assertEqual(approved["models"], [{"id": "mdl-1", "label": "Baseline"}])
        self.assertEqual(approved["experiments"],
                         [{"id": "exp-1", "label": "Compare",
                           "benchmark_id": "public-test", "cases": 12}])
        self.assertEqual(set(approved), {"datasets", "models", "experiments"})


def instance(**overrides):
    from lifemate_api.catalog import ExperimentInstance

    fields = dict(
        experiment_id="exp-instance-1",
        template_id="exp-1",
        benchmark_id="public-test",
        dataset_id="ds-1",
        model_id="mdl-1",
        label="Compare",
        decoding={"temperature": 0.0},
        mode="agent",
        content_hash="c" * 64,
        created_by="alice",
        created_at="2026-10-30T12:00:00+00:00",
    )
    fields.update(overrides)
    return ExperimentInstance(**fields)


class TemplateResolutionTests(unittest.TestCase):
    def test_a_create_body_needs_only_a_template_dataset_and_model(self):
        template, dataset, model, label = catalog().resolve_template(
            "exp-1", {"template_id": "exp-1", "dataset_id": "ds-1", "model_id": "mdl-1"})
        self.assertEqual(template.benchmark_id, "public-test")
        self.assertEqual(dataset.id, "ds-1")
        self.assertEqual(model.id, "mdl-1")
        self.assertEqual(label, "Compare")

    def test_a_custom_label_is_kept_and_other_fields_are_refused(self):
        _, _, _, label = catalog().resolve_template(
            "exp-1", {"dataset_id": "ds-1", "model_id": "mdl-1", "label": "Mine"})
        self.assertEqual(label, "Mine")
        for name, value in (("benchmark_id", "x"), ("content_hash", "a" * 64),
                            ("decoding", {}), ("machine_type", "g2-standard-8"),
                            ("image_digest", "sha256:" + "f" * 64)):
            with self.assertRaises(UnknownArtifact, msg=name):
                catalog().resolve_template("exp-1", {"dataset_id": "ds-1", "model_id": "mdl-1",
                                                     name: value})

    def test_an_unknown_template_or_artifact_is_refused(self):
        for template_id, body in (
            ("exp-9", {"dataset_id": "ds-1", "model_id": "mdl-1"}),
            ("exp-1", {"dataset_id": "ds-9", "model_id": "mdl-1"}),
            ("exp-1", {"dataset_id": "ds-1", "model_id": "mdl-9"}),
        ):
            with self.assertRaises(UnknownArtifact, msg=template_id):
                catalog().resolve_template(template_id, body)

    def test_an_instance_resolves_through_its_template(self):
        resolved = catalog().resolve("exp-instance-1", {"dataset_id": "ds-1", "model_id": "mdl-1"},
                                     instance=instance())
        self.assertEqual(resolved.benchmark_id, "public-test")
        self.assertEqual(resolved.mode, "agent")
        self.assertEqual(resolved.dataset_id, "ds-1")
        self.assertEqual(resolved.model_id, "mdl-1")

    def test_an_instance_submission_cannot_change_dataset_or_model(self):
        # Registry has one dataset/model, so changing an id is an unknown id; the
        # mismatch check still refuses before any request is built.
        with self.assertRaises(UnknownArtifact):
            catalog().resolve("exp-instance-1", {"dataset_id": "ds-9", "model_id": "mdl-1"},
                              instance=instance())

    def test_experiment_for_names_the_instance_or_refuses(self):
        stored = instance()
        self.assertIs(catalog().experiment_for("exp-instance-1",
                                               lambda _id: stored), stored)
        with self.assertRaises(UnknownArtifact):
            catalog().experiment_for("exp-missing", lambda _id: None)


class AdapterImportTests(unittest.TestCase):
    def test_adapters_import_without_google_clients(self):
        from lifemate_api.store import firestore_repository
        from lifemate_api.tasks import CloudTasksEnqueuer, RecordingEnqueuer

        self.assertTrue(callable(firestore_repository))
        self.assertTrue(callable(CloudTasksEnqueuer))
        self.assertEqual(RecordingEnqueuer().enqueued, [])

    def test_firestore_repository_accepts_an_injected_client(self):
        from lifemate_api.store import FirestoreRepository

        class Collection:
            def __init__(self, name):
                self.name = name

        class Client:
            def collection(self, name):
                return Collection(name)

        repository = FirestoreRepository(Client())
        self.assertTrue(hasattr(repository, "commit_acceptance"))


if __name__ == "__main__":
    unittest.main()
