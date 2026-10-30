"""Request identity is the hash of a canonical payload, not of dict insertion order."""
import json
import unittest

from lifemate_cloud.errors import Conflict
from lifemate_cloud.requests import RunRequest, canonical_json


def sample(**overrides):
    fields = dict(
        dataset_id="ds-1",
        dataset_hash="a" * 64,
        model_id="mdl-1",
        model_hash="b" * 64,
        mode="agent",
        decoding={"temperature": 0.0, "top_p": 1.0, "schema": "lifemate-v1"},
        benchmark_id="public-test",
        machine_type="g2-standard-8",
        region="asia-southeast1",
        timeout_seconds=1800,
        retry_allowance=0,
        source_sha="c" * 40,
        image_digest="sha256:" + "d" * 64,
        inputs={"models/mdl-1.bin": 12345, "datasets/ds-1.jsonl": 99},
    )
    fields.update(overrides)
    return RunRequest(**fields)


class CanonicalRequestTests(unittest.TestCase):
    def test_same_content_in_any_key_order_has_one_identity(self):
        left = sample(decoding={"top_p": 1.0, "schema": "lifemate-v1", "temperature": 0.0},
                      inputs={"datasets/ds-1.jsonl": 99, "models/mdl-1.bin": 12345})
        right = sample()
        self.assertEqual(left.fingerprint(), right.fingerprint())
        self.assertEqual(canonical_json(left), canonical_json(right))

    def test_any_changed_field_changes_identity(self):
        base = sample().fingerprint()
        for change in (
            {"dataset_hash": "e" * 64},
            {"region": "us-central1"},
            {"retry_allowance": 1},
            {"inputs": {"models/mdl-1.bin": 12346, "datasets/ds-1.jsonl": 99}},
        ):
            self.assertNotEqual(base, sample(**change).fingerprint(), change)

    def test_fingerprint_is_sha256_hex_and_request_is_immutable(self):
        request = sample()
        self.assertRegex(request.fingerprint(), r"^[0-9a-f]{64}$")
        with self.assertRaises(Exception):
            request.region = "us-central1"

    def test_canonical_json_round_trips_to_the_same_fingerprint(self):
        request = sample()
        reloaded = RunRequest.from_payload(json.loads(canonical_json(request)))
        self.assertEqual(reloaded, request)
        self.assertEqual(reloaded.fingerprint(), request.fingerprint())

    def test_blank_identity_fields_are_rejected(self):
        for field in ("dataset_id", "model_id", "benchmark_id", "image_digest", "source_sha"):
            with self.assertRaises(ValueError, msg=field):
                sample(**{field: ""})

    def test_unknown_payload_field_is_rejected(self):
        payload = json.loads(canonical_json(sample()))
        payload["arbitrary_shell_command"] = "rm -rf /"
        with self.assertRaises(Conflict):
            RunRequest.from_payload(payload)


if __name__ == "__main__":
    unittest.main()
