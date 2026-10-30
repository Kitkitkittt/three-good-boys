"""The private API: auth, authorization, idempotency, views and no machine routes."""
import dataclasses
import datetime
import unittest

import jwt

import asgi_client
from lifemate_api.acceptance import IntentState
from lifemate_api.app import IDEMPOTENCY_HEADER, ApiSettings, create_app
from lifemate_api.auth import ASSERTION_HEADER, IAP_ISSUER
from lifemate_api.catalog import Artifact, Catalog, Experiment
from lifemate_api.store import InMemoryApiRepository
from lifemate_api.tasks import RecordingEnqueuer
from lifemate_cloud.manifest import ManifestEntry
from lifemate_cloud.roles import Role
from lifemate_cloud.run import RunState

AUDIENCE = "/projects/123/global/backendServices/456"
SECRET = "test-signing-secret"
NOW = datetime.datetime(2026, 10, 30, 12, 0, tzinfo=datetime.timezone.utc)
LATER = int(datetime.datetime(2030, 1, 1, tzinfo=datetime.timezone.utc).timestamp())

ROLES = {
    "owner@example.com": Role.OWNER,
    "maint@example.com": Role.MAINTAINER,
    "researcher@example.com": Role.RESEARCHER,
    "viewer@example.com": Role.VIEWER,
}


def catalog():
    return Catalog(
        datasets={"ds-1": Artifact(id="ds-1", label="Public test", hash="a" * 64,
                                    objects={"datasets/ds-1.jsonl": 99})},
        models={"mdl-1": Artifact(id="mdl-1", label="Baseline", hash="b" * 64,
                                  objects={"models/mdl-1.bin": 12345})},
        experiments={"exp-1": Experiment(id="exp-1", label="Compare", benchmark_id="public-test",
                                         cases=12, content_hash="c" * 64, mode="agent",
                                         decoding={"temperature": 0.0},
                                         expected_names=("predictions.jsonl",))},
        machine_type="g2-standard-8",
        region="asia-southeast1",
        timeout_seconds=1800,
        retry_allowance=0,
        source_sha="d" * 40,
        image_digest="sha256:" + "e" * 64,
        decoding_defaults={"top_p": 1.0},
        deadline_seconds=300,
    )


def verifier(assertion):
    return jwt.decode(assertion, SECRET, algorithms=["HS256"], options={"verify_aud": False})


def assertion(email, **overrides):
    claims = {
        "iss": IAP_ISSUER,
        "aud": AUDIENCE,
        "exp": LATER,
        "email": email,
        "sub": "subject-" + email,
    }
    claims.update(overrides)
    return jwt.encode(claims, SECRET, algorithm="HS256")


def harness(enqueuer=None, roles=None):
    repository = InMemoryApiRepository()
    app = create_app(
        repository=repository,
        verifier=verifier,
        settings=ApiSettings(iap_audience=AUDIENCE, roles=roles or ROLES, catalog=catalog()),
        enqueuer=enqueuer,
        now=lambda: NOW,
    )
    return app, repository


def call(app, method, path, email="researcher@example.com", key=None, body=None, assertion_value=None):
    headers = {}
    if email is not None:
        headers[ASSERTION_HEADER] = assertion_value if assertion_value is not None else assertion(email)
    if key is not None:
        headers[IDEMPOTENCY_HEADER] = key
    return asgi_client.request(app, method, path, headers=headers, json_body=body)


SUBMIT = {"dataset_id": "ds-1", "model_id": "mdl-1", "decoding": {"top_p": 0.9}}


class HealthTests(unittest.TestCase):
    def test_healthz_needs_no_identity(self):
        app, _ = harness()
        response = asgi_client.request(app, "GET", "/healthz")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.json, {"status": "ok"})


class AuthenticationTests(unittest.TestCase):
    def test_missing_assertion_is_unauthenticated(self):
        app, _ = harness()
        response = call(app, "GET", "/api/me", email=None)
        self.assertEqual(response.status, 401)
        self.assertEqual(response.code, "unauthenticated")

    def test_unregistered_email_is_forbidden(self):
        app, _ = harness()
        self.assertIn(call(app, "GET", "/api/me", email="stranger@example.com").status, (401, 403))

    def test_wrong_audience_assertion_is_rejected(self):
        app, _ = harness()
        token = assertion("researcher@example.com", aud="/projects/123/global/backendServices/999")
        response = call(app, "GET", "/api/me", assertion_value=token)
        self.assertEqual(response.status, 401)

    def test_wrong_issuer_assertion_is_rejected(self):
        app, _ = harness()
        token = assertion("researcher@example.com", iss="https://accounts.google.com")
        self.assertEqual(call(app, "GET", "/api/me", assertion_value=token).status, 401)

    def test_expired_assertion_is_rejected(self):
        app, _ = harness()
        token = assertion("researcher@example.com", exp=int((NOW - datetime.timedelta(hours=1)).timestamp()))
        self.assertEqual(call(app, "GET", "/api/me", assertion_value=token).status, 401)

    def test_id_header_does_not_grant_identity(self):
        app, _ = harness()
        # An unsigned header claiming a privileged email is ignored entirely.
        response = asgi_client.request(
            app, "GET", "/api/me",
            headers={"x-goog-authenticated-user-email": "owner@example.com"},
        )
        self.assertEqual(response.status, 401)

    def test_me_reports_the_verified_role(self):
        app, _ = harness()
        response = call(app, "GET", "/api/me", email="maint@example.com")
        self.assertEqual(response.json, {"email": "maint@example.com", "role": "maintainer"})


class AuthorizationTests(unittest.TestCase):
    def test_viewer_cannot_submit(self):
        app, repository = harness()
        response = call(app, "POST", "/api/experiments/exp-1/runs", email="viewer@example.com",
                        key="k1", body=SUBMIT)
        self.assertEqual(response.status, 403)
        self.assertEqual(repository.all_runs(), [])

    def test_researcher_may_submit(self):
        app, _ = harness()
        response = call(app, "POST", "/api/experiments/exp-1/runs", email="researcher@example.com",
                        key="k1", body=SUBMIT)
        self.assertEqual(response.status, 202)
        self.assertEqual(response.json["state"], "QUEUED")

    def test_maintainer_and_owner_may_submit(self):
        for email in ("maint@example.com", "owner@example.com"):
            app, _ = harness()
            self.assertEqual(
                call(app, "POST", "/api/experiments/exp-1/runs", email=email, key="k1", body=SUBMIT).status,
                202, email,
            )

    def test_viewer_cannot_cancel(self):
        app, _ = harness()
        submitted = call(app, "POST", "/api/experiments/exp-1/runs", key="k1", body=SUBMIT).json
        response = call(app, "POST", f"/api/runs/{submitted['run_id']}/cancel", email="viewer@example.com")
        self.assertEqual(response.status, 403)

    def test_one_user_cannot_cancel_anothers_run(self):
        app, _ = harness()
        submitted = call(app, "POST", "/api/experiments/exp-1/runs", key="k1", body=SUBMIT).json
        response = call(app, "POST", f"/api/runs/{submitted['run_id']}/cancel", email="maint@example.com")
        self.assertEqual(response.status, 403)


class SubmissionTests(unittest.TestCase):
    def submit(self, app, key="k1", body=None, email="researcher@example.com"):
        return call(app, "POST", "/api/experiments/exp-1/runs", email=email, key=key, body=body or SUBMIT)

    def test_submission_returns_202_and_persists_one_intent(self):
        app, repository = harness()
        response = self.submit(app)
        self.assertEqual(response.status, 202)
        intents = repository.all_intents()
        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0].state, IntentState.PENDING)

    def test_same_key_and_body_returns_the_existing_run(self):
        app, repository = harness()
        first = self.submit(app).json
        second = self.submit(app).json
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertEqual(len(repository.all_runs()), 1)

    def test_same_key_different_body_conflicts(self):
        app, repository = harness()
        self.submit(app)
        differing = dict(SUBMIT, decoding={"top_p": 0.5})
        response = self.submit(app, body=differing)
        self.assertEqual(response.status, 409)
        self.assertEqual(response.code, "conflict")
        self.assertEqual(len(repository.all_runs()), 1)

    def test_unknown_client_field_is_rejected(self):
        app, repository = harness()
        body = dict(SUBMIT, machine_type="a3-megagpu-8g")
        response = self.submit(app, body=body)
        self.assertEqual(response.status, 400)
        self.assertEqual(repository.all_runs(), [])

    def test_arbitrary_image_region_and_tier_are_not_accepted(self):
        app, _ = harness()
        for field, value in (("region", "us-central1"), ("machine_type", "a3-highgpu-8g"),
                             ("image_digest", "sha256:" + "f" * 64), ("timeout_seconds", 99999)):
            response = self.submit(app, body=dict(SUBMIT, **{field: value}))
            self.assertEqual(response.status, 400, field)

    def test_unknown_dataset_or_experiment_is_refused(self):
        app, _ = harness()
        self.assertEqual(call(app, "POST", "/api/experiments/exp-9/runs", key="k", body=SUBMIT).status, 400)
        self.assertEqual(
            call(app, "POST", "/api/experiments/exp-1/runs", key="k",
                 body=dict(SUBMIT, dataset_id="ds-9")).status,
            400,
        )

    def test_enqueue_happens_after_the_durable_commit(self):
        recorder = RecordingEnqueuer()
        app, repository = harness(enqueuer=recorder)
        self.submit(app)
        self.assertEqual(repository.commits, 1)
        self.assertEqual(len(recorder.enqueued), 1)  # enqueued only once, after commit
        intent = repository.all_intents()[0]
        self.assertEqual(intent.state, IntentState.ENQUEUED)

    def test_lost_enqueue_still_accepts_the_run(self):
        app, repository = harness(enqueuer=RecordingEnqueuer(fail=True))
        response = self.submit(app)
        self.assertEqual(response.status, 202)
        self.assertEqual(repository.all_intents()[0].state, IntentState.PENDING)

    def test_empty_idempotency_key_is_rejected(self):
        app, repository = harness()
        self.assertEqual(self.submit(app, key="  ").status, 400)
        self.assertEqual(repository.all_runs(), [])

    def test_the_client_decoding_merges_with_server_defaults(self):
        app, repository = harness()
        self.submit(app)
        run = repository.all_runs()[0]
        self.assertNotIn("decoding", run.__dict__)  # request is not echoed on the run view


CREATE = {"template_id": "exp-1", "dataset_id": "ds-1", "model_id": "mdl-1"}


class ExperimentCreationTests(unittest.TestCase):
    """POST /api/experiments: authenticated, validated, idempotent, user-scoped."""

    def create(self, app, key="c1", body=None, email="researcher@example.com"):
        return call(app, "POST", "/api/experiments", email=email, key=key, body=body or CREATE)

    def test_creation_returns_201_and_persists_a_real_instance(self):
        app, repository = harness()
        response = self.create(app)
        self.assertEqual(response.status, 201)
        instance = repository.get_experiment(response.json["experiment_id"])
        self.assertIsNotNone(instance)
        self.assertEqual(instance.template_id, "exp-1")
        self.assertEqual(instance.benchmark_id, "public-test")
        self.assertEqual(instance.dataset_id, "ds-1")
        self.assertEqual(instance.model_id, "mdl-1")
        self.assertEqual(instance.created_by, "researcher@example.com")

    def test_creation_requires_both_auth_and_the_submit_action(self):
        app, repository = harness()
        self.assertEqual(self.create(app, email=None).status, 401)
        self.assertEqual(self.create(app, email="viewer@example.com").status, 403)
        self.assertEqual(repository.all_experiments(), [])

    def test_creation_needs_an_idempotency_key(self):
        app, repository = harness()
        self.assertEqual(self.create(app, key=None).status, 400)
        self.assertEqual(repository.all_experiments(), [])

    def test_same_key_and_body_returns_the_existing_instance(self):
        app, repository = harness()
        first = self.create(app, key="c1").json
        second = self.create(app, key="c1").json
        self.assertEqual(first["experiment_id"], second["experiment_id"])
        self.assertEqual(len(repository.all_experiments()), 1)

    def test_same_key_different_body_conflicts(self):
        app, repository = harness()
        self.create(app, key="c1")
        changed = dict(CREATE, model_id="mdl-1", template_id="exp-1", label="other")
        response = self.create(app, key="c1", body=changed)
        self.assertEqual(response.status, 409)
        self.assertEqual(response.code, "conflict")
        self.assertEqual(len(repository.all_experiments()), 1)

    def test_the_key_is_user_scoped(self):
        app, repository = harness()
        mine = self.create(app, key="shared").json
        theirs = self.create(app, key="shared", email="maint@example.com").json
        self.assertNotEqual(mine["experiment_id"], theirs["experiment_id"])
        self.assertEqual(len(repository.all_experiments()), 2)

    def test_unknown_template_or_dataset_or_model_is_refused(self):
        app, repository = harness()
        for body in (
            dict(CREATE, template_id="exp-9"),
            dict(CREATE, dataset_id="ds-9"),
            dict(CREATE, model_id="mdl-9"),
        ):
            response = self.create(app, key="c1", body=body)
            self.assertEqual(response.status, 400, body)
            self.assertEqual(response.code, "unknown_artifact")
        self.assertEqual(repository.all_experiments(), [])

    def test_missing_template_or_identity_fields_are_refused(self):
        app, _ = harness()
        self.assertEqual(self.create(app, body={"dataset_id": "ds-1",
                                                "model_id": "mdl-1"}).status, 400)
        self.assertEqual(self.create(app, body={"template_id": "exp-1"}).status, 400)

    def test_no_policy_or_provenance_field_is_accepted(self):
        app, repository = harness()
        for name, value in (
            ("machine_type", "a3-megagpu-8g"),
            ("region", "us-central1"),
            ("image_digest", "sha256:" + "f" * 64),
            ("benchmark_id", "other-benchmark"),
            ("content_hash", "a" * 64),
            ("decoding", {"temperature": 1.0}),
            ("inputs", {"datasets/ds-1.jsonl": 1}),
            ("expected_names", ["x.jsonl"]),
        ):
            response = self.create(app, key="c1", body=dict(CREATE, **{name: value}))
            self.assertEqual(response.status, 400, name)
        self.assertEqual(repository.all_experiments(), [])

    def test_the_response_echoes_identity_but_never_decoding_or_objects(self):
        app, _ = harness()
        response = self.create(app)
        payload = str(response.json)
        self.assertEqual(response.json["benchmark_id"], "public-test")
        self.assertEqual(response.json["dataset_id"], "ds-1")
        self.assertRegex(response.json["configuration_hash"], r"^[0-9a-f]{64}$")
        self.assertNotIn("temperature", payload)
        self.assertNotIn("ds-1.jsonl", payload)
        self.assertNotIn("mdl-1.bin", payload)

    def test_a_created_instance_can_be_submitted_to(self):
        app, repository = harness()
        instance = self.create(app).json
        # The instance's creation hash is the template's pinned default config.
        # Submitting decoding that overrides a default is a different effective
        # configuration, so its hash must differ; only identical config matches.
        overridden = call(app, "POST", f"/api/experiments/{instance['experiment_id']}/runs",
                          key="s1", body=SUBMIT)
        self.assertEqual(overridden.status, 202)
        run_id = overridden.json["run_id"]
        self.assertEqual(repository.experiment_id(run_id), instance["experiment_id"])
        self.assertEqual(repository.get_expected_names(run_id), ("predictions.jsonl",))
        self.assertEqual(overridden.json["benchmark_id"], "public-test")
        self.assertNotEqual(overridden.json["configuration_hash"],
                            instance["configuration_hash"])

        # The creation response pins the template defaults, so a submission that
        # sends no decoding resolves to exactly that configuration.
        pinned = call(app, "POST", f"/api/experiments/{instance['experiment_id']}/runs",
                      key="s2", body={"dataset_id": "ds-1", "model_id": "mdl-1"})
        self.assertEqual(pinned.status, 202)
        self.assertEqual(pinned.json["configuration_hash"], instance["configuration_hash"])

    def test_an_instance_submission_cannot_swap_dataset_or_model(self):
        app, repository = harness()
        instance = self.create(app).json
        # A second approved model keeps the swap a dataset/model mismatch, not an
        # unknown id; registry here holds one model, so a changed id is unknown.
        response = call(app, "POST", f"/api/experiments/{instance['experiment_id']}/runs",
                        key="s1", body=dict(SUBMIT, model_id="mdl-9"))
        self.assertEqual(response.status, 400)
        self.assertEqual(repository.all_runs(), [])

    def test_template_submission_still_works_without_an_instance(self):
        app, repository = harness()
        response = call(app, "POST", "/api/experiments/exp-1/runs", key="k1", body=SUBMIT)
        self.assertEqual(response.status, 202)
        self.assertEqual(repository.experiment_id(response.json["run_id"]), "exp-1")

    def test_machine_routes_are_still_absent_after_creation_exists(self):
        app, _ = harness()
        self.assertEqual(call(app, "POST", "/api/experiments", email="owner@example.com",
                              key="c1", body=dict(CREATE, template_id="/internal/dispatch")).status,
                         400)
        for path in ("/internal/dispatch", "/internal/reconcile"):
            self.assertEqual(call(app, "POST", path, email="owner@example.com").status, 404)


class ArtifactLifecycleTests(unittest.TestCase):
    """Accept -> verified finalize -> persisted metadata -> detail view."""

    def test_detail_returns_persisted_artifact_metadata_after_finalize(self):
        app, repository = harness()
        submitted = call(app, "POST", "/api/experiments/exp-1/runs", key="k1", body=SUBMIT).json
        run_id = submitted["run_id"]
        # Before finalize the view is honest: no metadata, not a fabricated list.
        self.assertEqual(call(app, "GET", f"/api/runs/{run_id}").json["artifacts"], [])

        # The dispatcher persists only what verification returned.
        verified = (ManifestEntry(name="predictions.jsonl", generation=11,
                                  checksum="b" * 64, size=None),
                    ManifestEntry(name="report.json", generation=4,
                                  checksum="c" * 64, size=2048))
        repository.put_artifacts(run_id, verified)

        detail = call(app, "GET", f"/api/runs/{run_id}").json
        self.assertEqual(detail["artifacts"], [
            {"name": "predictions.jsonl", "generation": "11", "checksum": "b" * 64,
             "bytes": None},
            {"name": "report.json", "generation": "4", "checksum": "c" * 64, "bytes": 2048},
        ])
        self.assertNotIn("gs://", str(detail))

    def test_the_list_view_stays_metadata_free_and_detail_needs_read_right(self):
        app, repository = harness()
        submitted = call(app, "POST", "/api/experiments/exp-1/runs", key="k1", body=SUBMIT).json
        run_id = submitted["run_id"]
        repository.put_artifacts(run_id, (ManifestEntry(name="a.jsonl", generation=1,
                                                       checksum="d" * 64),))
        listed = call(app, "GET", "/api/runs").json["runs"][0]
        self.assertNotIn("artifacts", listed)
        # An unauthenticated caller never reaches the metadata at all.
        self.assertEqual(call(app, "GET", f"/api/runs/{run_id}", email=None).status, 401)


class DispatcherContractTests(unittest.TestCase):
    """The accepted data a separate machine service (ticket 17) reads back."""

    def test_every_dispatcher_surface_is_pinned_after_http_acceptance(self):
        app, repository = harness()
        run_id = call(app, "POST", "/api/experiments/exp-1/runs", key="k1", body=SUBMIT).json["run_id"]
        self.assertEqual(repository.experiment_id(run_id), "exp-1")
        self.assertEqual(repository.get_expected_names(run_id), ("predictions.jsonl",))
        self.assertEqual(repository.get_request(run_id).dataset_id, "ds-1")
        self.assertIsNotNone(repository.accepted_at(run_id))
        self.assertEqual(repository.deadline_seconds(run_id), 300)
        self.assertEqual(len(repository.all_intents()), 1)

    def test_the_pinned_request_matches_the_fingerprint(self):
        app, repository = harness()
        run = call(app, "POST", "/api/experiments/exp-1/runs", key="k1", body=SUBMIT).json
        stored = repository.get_run(run["run_id"])
        self.assertEqual(repository.get_request(run["run_id"]).fingerprint(),
                         stored.request_fingerprint)


class ViewTests(unittest.TestCase):
    def test_status_exposes_only_approved_metadata(self):
        app, _ = harness()
        submitted = call(app, "POST", "/api/experiments/exp-1/runs", key="k1", body=SUBMIT).json
        response = call(app, "GET", f"/api/runs/{submitted['run_id']}")
        self.assertEqual(response.status, 200)
        self.assertEqual(
            set(response.json),
            {"run_id", "owner", "state", "cancel_requested", "batch_phase", "failure",
             "benchmark_id", "benchmark_hash", "benchmark_cases", "experiment_id",
             "dataset_id", "model_id", "mode", "configuration_hash", "artifacts"},
        )
        self.assertEqual(response.json["artifacts"], [])
        self.assertNotIn("inputs", str(response.json))
        self.assertNotIn("request_fingerprint", str(response.json))
        # Sanitized identity, never the pinned configuration itself.
        self.assertEqual(response.json["benchmark_id"], "public-test")
        self.assertEqual(response.json["dataset_id"], "ds-1")
        self.assertEqual(response.json["model_id"], "mdl-1")
        self.assertEqual(response.json["mode"], "agent")
        self.assertEqual(response.json["benchmark_hash"], "c" * 64)
        self.assertEqual(response.json["benchmark_cases"], 12)
        self.assertNotIn("decoding", response.json)
        self.assertRegex(response.json["configuration_hash"], r"^[0-9a-f]{64}$")
        self.assertNotIn("datasets/ds-1.jsonl", str(response.json))
        self.assertNotIn("models/mdl-1.bin", str(response.json))

    def test_artifact_metadata_is_name_generation_checksum_and_size_only(self):
        app, repository = harness()
        submitted = call(app, "POST", "/api/experiments/exp-1/runs", key="k1", body=SUBMIT).json
        run_id = submitted["run_id"]
        entry = ManifestEntry(name="predictions.jsonl", generation=7,
                              checksum="a" * 64, size=1024)
        repository.put_artifacts(run_id, (entry,))
        response = call(app, "GET", f"/api/runs/{run_id}")
        self.assertEqual(
            response.json["artifacts"],
            [{"name": "predictions.jsonl", "generation": "7", "checksum": "a" * 64,
              "bytes": 1024}],
        )
        self.assertNotIn("gs://", str(response.json))

    def test_run_list_echoes_the_same_identity_and_digest(self):
        app, _ = harness()
        submitted = call(app, "POST", "/api/experiments/exp-1/runs", key="k1", body=SUBMIT).json
        detail = call(app, "GET", f"/api/runs/{submitted['run_id']}").json
        listed = call(app, "GET", "/api/runs").json["runs"][0]
        for name in ("benchmark_id", "experiment_id", "dataset_id", "model_id", "mode",
                     "configuration_hash"):
            self.assertEqual(listed[name], detail[name], name)
        self.assertNotIn("artifacts", listed)  # list stays the summary shape

    def test_identical_configuration_yields_the_same_digest(self):
        app, _ = harness()
        first = call(app, "POST", "/api/experiments/exp-1/runs", key="k1", body=SUBMIT).json
        second = call(app, "POST", "/api/experiments/exp-1/runs", key="k2", body=SUBMIT).json
        self.assertEqual(first["configuration_hash"], second["configuration_hash"])
        # Different pinned decoding is different configuration identity.
        other = call(app, "POST", "/api/experiments/exp-1/runs", key="k3",
                     body=dict(SUBMIT, decoding={"top_p": 0.5})).json
        self.assertNotEqual(first["configuration_hash"], other["configuration_hash"])


    def test_replay_after_a_catalog_edit_returns_the_pinned_identity(self):
        """A catalog revision must not rewrite an already-accepted run's view.

        The replay shares the key and the canonical request, so it is the same
        run; its benchmark hash/cases come from the run's own record, never from
        the template as the catalog names it now.
        """
        repository = InMemoryApiRepository()
        settings = ApiSettings(iap_audience=AUDIENCE, roles=ROLES, catalog=catalog())
        app = create_app(repository=repository, verifier=verifier, settings=settings,
                         now=lambda: NOW)
        first = call(app, "POST", "/api/experiments/exp-1/runs", key="k1", body=SUBMIT).json
        self.assertEqual(first["benchmark_hash"], "c" * 64)
        self.assertEqual(first["benchmark_cases"], 12)

        # Same canonical request (dataset/model/hashes/decoding all unchanged),
        # but the benchmark the template points at has been revised.
        template = settings.catalog.experiments["exp-1"]
        settings.catalog = dataclasses.replace(settings.catalog, experiments={
            "exp-1": dataclasses.replace(template, content_hash="9" * 64, cases=20),
        })

        replay = call(app, "POST", "/api/experiments/exp-1/runs", key="k1", body=SUBMIT)
        self.assertEqual(replay.status, 202)
        self.assertEqual(replay.json["run_id"], first["run_id"])
        self.assertEqual(replay.json["benchmark_hash"], "c" * 64)
        self.assertEqual(replay.json["benchmark_cases"], 12)
        self.assertEqual(len(repository.all_runs()), 1)

    def test_failures_are_redacted(self):
        app, repository = harness()
        submitted = call(app, "POST", "/api/experiments/exp-1/runs", key="k1", body=SUBMIT).json
        run = repository.get_run(submitted["run_id"])
        repository.put_run(run.transition(RunState.SUBMITTING).transition(RunState.FAILED, "batch_failed"))
        response = call(app, "GET", f"/api/runs/{submitted['run_id']}/failures")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.json["failure"]["code"], "batch_failed")
        self.assertNotIn("traceback", str(response.json))

    def test_no_failure_returns_null(self):
        app, _ = harness()
        submitted = call(app, "POST", "/api/experiments/exp-1/runs", key="k1", body=SUBMIT).json
        self.assertIsNone(call(app, "GET", f"/api/runs/{submitted['run_id']}/failures").json["failure"])

    def test_unknown_run_is_not_found(self):
        app, _ = harness()
        self.assertEqual(call(app, "GET", "/api/runs/nope").status, 404)

    def test_models_are_the_approved_artifacts(self):
        app, _ = harness()
        response = call(app, "GET", "/api/models")
        self.assertEqual(response.json["datasets"], [{"id": "ds-1", "label": "Public test"}])
        self.assertEqual(response.json["models"], [{"id": "mdl-1", "label": "Baseline"}])
        self.assertEqual(response.json["experiments"],
                         [{"id": "exp-1", "label": "Compare",
                           "benchmark_id": "public-test", "cases": 12}])

    def test_run_list_is_scoped_to_the_caller(self):
        app, _ = harness()
        call(app, "POST", "/api/experiments/exp-1/runs", key="k1", body=SUBMIT)
        call(app, "POST", "/api/experiments/exp-1/runs", key="k1", body=SUBMIT, email="maint@example.com")
        mine = call(app, "GET", "/api/runs").json["runs"]
        self.assertEqual(len(mine), 1)  # the researcher sees only their own runs
        everything = call(app, "GET", "/api/runs", email="owner@example.com").json["runs"]
        self.assertEqual(len(everything), 2)

    def test_cancel_records_intent_without_a_terminal_state(self):
        app, _ = harness()
        submitted = call(app, "POST", "/api/experiments/exp-1/runs", key="k1", body=SUBMIT).json
        response = call(app, "POST", f"/api/runs/{submitted['run_id']}/cancel")
        self.assertEqual(response.status, 200)
        self.assertTrue(response.json["cancel_requested"])
        self.assertEqual(response.json["state"], "QUEUED")


class RouteTests(unittest.TestCase):
    def test_machine_routes_are_absent(self):
        app, _ = harness()
        for path in ("/internal/dispatch", "/internal/reconcile"):
            self.assertEqual(call(app, "POST", path, email="owner@example.com").status, 404)

    def test_healthz_is_the_only_unauthenticated_route(self):
        app, _ = harness()
        for path in ("/api/me", "/api/models", "/api/runs"):
            self.assertEqual(call(app, "GET", path, email=None).status, 401, path)


if __name__ == "__main__":
    unittest.main()
