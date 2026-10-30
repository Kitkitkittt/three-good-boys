"""A result is complete only when the manifest pins each required object once."""
import dataclasses
import unittest

from lifemate_cloud.errors import IncompleteManifest, ManifestConflict
from lifemate_cloud.manifest import ManifestEntry, ResultManifest

RUN = "run-1"


def entry(name, generation, checksum):
    return ManifestEntry(name=name, generation=generation, checksum=checksum, size=100)


def manifest(*required, run_id=RUN):
    return ResultManifest.create(run_id=run_id, required=required)


class ManifestTests(unittest.TestCase):
    def complete_manifest(self):
        return manifest("submission.jsonl", "samples/0001.json").add(
            entry("submission.jsonl", 5, "a" * 64)
        ).add(entry("samples/0001.json", 7, "b" * 64))

    def test_complete_coverage_verifies(self):
        result = self.complete_manifest()
        self.assertTrue(result.is_complete)
        result.verify_complete()
        self.assertEqual(
            [(e.name, e.generation, e.checksum) for e in result.entries],
            [("samples/0001.json", 7, "b" * 64), ("submission.jsonl", 5, "a" * 64)],
        )

    def test_missing_object_is_incomplete_and_verification_names_it(self):
        result = manifest("submission.jsonl", "samples/0001.json").add(
            entry("submission.jsonl", 5, "a" * 64)
        )
        self.assertFalse(result.is_complete)
        with self.assertRaises(IncompleteManifest) as caught:
            result.verify_complete()
        self.assertIn("samples/0001.json", str(caught.exception))

    def test_duplicate_coverage_is_refused(self):
        first = entry("submission.jsonl", 5, "a" * 64)
        duplicate = entry("submission.jsonl", 6, "a" * 64)
        with self.assertRaises(ManifestConflict):
            manifest("submission.jsonl").add(first).add(duplicate)

    def test_identical_repin_is_idempotent(self):
        once = manifest("submission.jsonl").add(entry("submission.jsonl", 5, "a" * 64))
        twice = once.add(entry("submission.jsonl", 5, "a" * 64))
        self.assertEqual(once, twice)

    def test_same_name_with_different_generation_or_checksum_conflicts(self):
        pinned = manifest("submission.jsonl").add(entry("submission.jsonl", 5, "a" * 64))
        for conflicting in (
            entry("submission.jsonl", 6, "a" * 64),
            entry("submission.jsonl", 5, "c" * 64),
        ):
            with self.assertRaises(ManifestConflict):
                pinned.add(conflicting)

    def test_unrequired_object_is_refused(self):
        with self.assertRaises(IncompleteManifest):
            manifest("submission.jsonl").add(entry("other.json", 1, "a" * 64))

    def test_generation_must_be_a_pinned_positive_int(self):
        for generation in (0, -3, "5"):
            with self.assertRaises(ValueError):
                entry("submission.jsonl", generation, "a" * 64)

    def test_checksum_must_be_sha256_hex(self):
        for checksum in ("abc", "g" * 64, "A" * 64):
            with self.assertRaises(ValueError):
                entry("submission.jsonl", 5, checksum)

    def test_manifest_is_immutable(self):
        result = self.complete_manifest()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            result.run_id = "other"

    def test_manifest_round_trips_through_a_dict(self):
        result = self.complete_manifest()
        self.assertEqual(ResultManifest.from_dict(result.to_dict()), result)

    def test_manifest_of_another_run_is_not_complete_for_this_run(self):
        foreign = ResultManifest.from_dict(dict(self.complete_manifest().to_dict(), run_id="run-2"))
        with self.assertRaises(IncompleteManifest):
            foreign.verify_for(RUN)


if __name__ == "__main__":
    unittest.main()
