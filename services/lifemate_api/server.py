"""Production entrypoint: build the app from environment configuration.

Kept separate from :mod:`lifemate_api.app` so tests never construct Google
clients. Only this module reads the environment and builds real adapters.

Environment:
- ``LIFEMATE_IAP_AUDIENCE``: the IAP backend-service audience this instance serves.
- ``LIFEMATE_ROLES``: JSON object mapping verified email -> role.
- ``LIFEMATE_CATALOG``: JSON object with the owner-registered datasets/models/
  experiments and the deployment policy (tier, region, timeout, retries, image).
- ``LIFEMATE_DISPATCH_URL``, ``LIFEMATE_TASKS_QUEUE``, ``LIFEMATE_TASKS_LOCATION``,
  ``LIFEMATE_TASKS_SA``: Cloud Tasks dispatch target. Enqueue is disabled when the
  URL is absent, so admission still works and the reconciler repairs later.
- ``GOOGLE_CLOUD_PROJECT``, ``LIFEMATE_FIRESTORE_DATABASE``: Firestore target.
"""
import json
import os

from lifemate_cloud.roles import Role

from .app import ApiSettings, create_app
from .auth import iap_verifier
from .catalog import Artifact, Catalog, Experiment
from .store import firestore_repository
from .tasks import CloudTasksEnqueuer


def _roles(raw):
    return {email: Role(role) for email, role in json.loads(raw or "{}").items()}


def _catalog(raw):
    document = json.loads(raw)
    return Catalog(
        datasets={
            item["id"]: Artifact(id=item["id"], label=item.get("label", item["id"]),
                                 hash=item["hash"], objects=item.get("objects", {}))
            for item in document["datasets"]
        },
        models={
            item["id"]: Artifact(id=item["id"], label=item.get("label", item["id"]),
                                 hash=item["hash"], objects=item.get("objects", {}))
            for item in document["models"]
        },
        experiments={
            item["id"]: Experiment(id=item["id"], label=item.get("label", item["id"]),
                                   benchmark_id=item["benchmark_id"], cases=item.get("cases", 0),
                                   content_hash=item.get("content_hash", ""),
                                   mode=item.get("mode", "agent"),
                                   decoding=item.get("decoding", {}),
                                   expected_names=tuple(item.get("expected_names", ())))
            for item in document["experiments"]
        },
        machine_type=document["machine_type"],
        region=document["region"],
        timeout_seconds=document["timeout_seconds"],
        retry_allowance=document.get("retry_allowance", 0),
        source_sha=document["source_sha"],
        image_digest=document["image_digest"],
        decoding_defaults=document.get("decoding_defaults", {}),
        deadline_seconds=document.get("deadline_seconds"),
    )


def _enqueuer(env):
    url = env.get("LIFEMATE_DISPATCH_URL")
    if not url:
        return None
    return CloudTasksEnqueuer(
        project=env["GOOGLE_CLOUD_PROJECT"],
        location=env["LIFEMATE_TASKS_LOCATION"],
        queue=env["LIFEMATE_TASKS_QUEUE"],
        dispatch_url=url,
        service_account=env["LIFEMATE_TASKS_SA"],
        audience=env["LIFEMATE_DISPATCH_AUDIENCE"],
    )


def build_from_env(env=None):
    env = env if env is not None else os.environ
    repository = firestore_repository(
        project=env.get("GOOGLE_CLOUD_PROJECT"),
        database=env.get("LIFEMATE_FIRESTORE_DATABASE"),
    )
    settings = ApiSettings(
        iap_audience=env["LIFEMATE_IAP_AUDIENCE"],
        roles=_roles(env.get("LIFEMATE_ROLES")),
        catalog=_catalog(env["LIFEMATE_CATALOG"]),
    )
    return create_app(
        repository=repository,
        verifier=iap_verifier(env["LIFEMATE_IAP_AUDIENCE"]),
        settings=settings,
        enqueuer=_enqueuer(env),
    )


def app():
    """ASGI factory: ``uvicorn lifemate_api.server:app --factory``."""
    return build_from_env()
