"""In-memory artifact store: conditional create, generation-pinned reads, verified pinning."""
import unittest

from lifemate_cloud.artifacts import InMemoryArtifactStore
from lifemate_cloud.errors import Conflict, IncompleteManifest, ManifestConflict
from lifemate_cloud.manifest import ResultManifest


def store():
    return InMemoryArtifactStore()


class ConditionalCreateTests(unittest.TestCase):
    def test_first_write_creates_generation_one(self):
        pinned = store().put_if_absent("results/run-1/submission.jsonl", b"x")
        self.assertEqual(pinned.generation, 1)

    def test_identical_rewrite_reuses_the_existing_object(self):
        artifacts = store()
        first = artifacts.put_if_absent("results/run-1/a.json", b"x")
        self.assertEqual(artifacts.put_if_absent("results/run-1/a.json", b"x"), first)

    def test_different_content_never_overwrites(self):
        artifacts = store()
        artifacts.put_if_absent("results/run-1/a.json", b"x")
        with self.assertRaises(Conflict):
            artifacts.put_if_absent("results/run-1/a.json", b"y")
        self.assertEqual(artifacts.read("results/run-1/a.json", generation=1), b"x")

    def test_conditional_match_requires_the_expected_generation(self):
        artifacts = store()
        artifacts.put_if_absent("a.json", b"x")
        with self.assertRaises(Conflict):
            artifacts.put_if_absent("a.json", b"y", if_generation_match=0)
        with self.assertRaises(Conflict):
            artifacts.put_if_absent("a.json", b"y", if_generation_match=1)

    def test_read_at_a_missing_generation_fails(self):
        with self.assertRaises(Conflict):
            store().read("absent.json", generation=1)


class ResultPinningTests(unittest.TestCase):
    def artifacts(self):
        artifacts = store()
        artifacts.put_if_absent("results/run-1/submission.jsonl", b"one")
        artifacts.put_if_absent("results/run-1/samples/0001.json", b"two")
        return artifacts

    def test_pinning_covers_every_object_with_generation_and_checksum(self):
        manifest = ResultManifest.create(
            run_id="run-1", required={"submission.jsonl", "samples/0001.json"}
        )
        pinned = self.artifacts().pin(manifest, prefix="results/run-1/")
        pinned.verify_complete()
        self.assertEqual([entry.name for entry in pinned.entries], ["samples/0001.json", "submission.jsonl"])
        self.assertEqual({entry.generation for entry in pinned.entries}, {1})
        self.assertTrue(all(len(entry.checksum) == 64 for entry in pinned.entries))

    def test_pinning_refuses_an_object_that_was_never_stored(self):
        manifest = ResultManifest.create(run_id="run-1", required={"submission.jsonl", "missing.json"})
        with self.assertRaises(IncompleteManifest):
            self.artifacts().pin(manifest, prefix="results/run-1/")

    def test_content_changed_after_pinning_is_detected(self):
        artifacts = self.artifacts()
        manifest = ResultManifest.create(
            run_id="run-1", required={"submission.jsonl", "samples/0001.json"}
        )
        pinned = artifacts.pin(manifest, prefix="results/run-1/")
        artifacts.replace_for_test("results/run-1/submission.jsonl", b"tampered")
        self.assertEqual(len(artifacts.generations_for_test("results/run-1/submission.jsonl")), 2)
        # A pinned generation stays readable and unchanged.
        artifacts.verify(pinned, prefix="results/run-1/")
        # Re-pinning sees the head move and refuses to accept the new content.
        with self.assertRaises(ManifestConflict):
            artifacts.pin(pinned, prefix="results/run-1/")

    def test_verify_fails_when_a_pinned_generation_is_gone(self):
        artifacts = self.artifacts()
        manifest = artifacts.pin(
            ResultManifest.create(run_id="run-1", required={"submission.jsonl"}),
            prefix="results/run-1/",
        )
        artifacts.drop_for_test("results/run-1/submission.jsonl")
        with self.assertRaises(Conflict):
            artifacts.verify(manifest, prefix="results/run-1/")


if __name__ == "__main__":
    unittest.main()
