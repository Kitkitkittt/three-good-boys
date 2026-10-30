"""Exercise the actual ASGI adapter without credentials or cloud calls."""
import pathlib
import re
import unittest

from asgi_client import request
from dispatcher.server import create_app
from test_dispatch import harness

RUN_TF = pathlib.Path(__file__).resolve().parents[1] / "infra" / "terraform" / "dev" / "run.tf"


class DispatcherServerTests(unittest.TestCase):
    def test_dispatch_and_scheduler_routes_call_the_existing_service(self):
        service, repository, _, _, _, batch, _, run = harness()
        app = create_app(service)
        response = request(app, "POST", "/internal/dispatch", json_body={"run_id": run.run_id, "cost": 100})
        self.assertEqual(response.status, 200)
        self.assertEqual(response.json["job_id"], repository.get_op(run.run_id).job_id)
        self.assertEqual(len(batch.creates), 1)
        response = request(app, "POST", "/internal/reconcile")
        self.assertEqual(response.status, 200)
        self.assertIn(run.run_id, response.json["runs"])

    def test_errors_are_mapped_without_payloads(self):
        service, _, _, _, _, batch, _, run = harness()
        app = create_app(service)
        bad = request(app, "POST", "/internal/dispatch", json_body={})
        self.assertEqual(bad.status, 400)
        invalid = request(app, "POST", "/internal/reconcile", json_body={"run_id": []})
        self.assertEqual(invalid.status, 400)
        overflow = request(app, "POST", "/internal/dispatch", json_body={"run_id": run.run_id, "cost": 100_001})
        self.assertEqual(overflow.status, 409)
        self.assertEqual(overflow.json, {"code": "ledgeroverflow"})
        self.assertFalse(batch.creates)
        self.assertEqual(request(app, "GET", "/internal/dispatch").status, 405)
        self.assertEqual(request(app, "GET", "/api/me").status, 404)

    def test_configured_liveness_probe_is_served(self):
        """The Cloud Run revision only becomes ready if its probe path answers."""
        paths = re.findall(r'http_get \{\s*path\s*=\s*"([^"]+)"', RUN_TF.read_text())
        self.assertTrue(paths, "no http_get probe in run.tf")
        service, _, _, _, _, _, _, _ = harness()
        for path in set(paths):
            response = request(create_app(service), "GET", path)
            self.assertEqual(response.status, 200, path)

    def test_healthz_needs_no_service(self):
        class Broken:
            def __getattr__(self, name):
                raise AssertionError("healthz touched the service")

        response = request(create_app(Broken()), "GET", "/healthz")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.json, {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
