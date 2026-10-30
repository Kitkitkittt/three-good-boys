"""Entry point: wire the real adapters and expose the two machine routes.

Importing this module is side-effect free; ``build_service`` builds the Google
clients lazily so unit tests never touch them. The runtime image's HTTP
framework (``dispatcher.server``) serves the same two callables.

Environment (deployment configuration, never request input):
- ``PROJECT_ID``, ``REGION``, ``FIRESTORE_DATABASE``: Firestore and Batch target.
- ``DISPATCH_URL``, ``DISPATCH_AUDIENCE``, ``TASK_SERVICE_ACCOUNT``,
  ``TASKS_LOCATION``, ``TASKS_QUEUE``: Cloud Tasks dispatch ingress. The task
  OIDC token identifies ``TASK_SERVICE_ACCOUNT``, which the Cloud Run service
  grants invoker rights to.
- ``RESULTS_BUCKET``, ``RESULT_PREFIX``: generation-pinned result verification.
- ``BUDGET_CENTS``, ``DEADLINE_SECONDS``: reservation and whole-run deadline.
- ``BATCH_IMAGE`` (digest), ``BATCH_SERVICE_ACCOUNT`` (the worker identity),
  ``BATCH_MACHINE_TYPE``, ``BATCH_BOOT_DISK_TYPE``, ``BATCH_BOOT_DISK_GB``,
  ``TASK_TIMEOUT_SECONDS``, ``BATCH_MAX_RETRIES``, ``BATCH_MOUNTS``
  (``bucket remote path [options]`` entries, ``;`` separated) and
  ``BATCH_ARGUMENTS`` (appended to the image ENTRYPOINT; never a shell command):
  the approved execution contract for the GPU job. The worker identity is
  separate from ``TASK_SERVICE_ACCOUNT`` so the machine invoker holds no worker
  rights.
"""
import json
import os
import sys

from . import google_adapters
from .http import handle_dispatch, handle_reconcile, status_for
from .service import DispatchPolicy, DispatchService
from .store import firestore_repository


def build_service(env=None):
    """Construct the production service from environment configuration."""
    env = os.environ if env is None else env
    from lifemate_api.store import firestore_repository as api_repository

    runs = api_repository(project=env["PROJECT_ID"], database=env.get("FIRESTORE_DATABASE"))
    client = runs._client
    return DispatchService(
        firestore_repository(client, runs),
        google_adapters.build_batch_client(env["PROJECT_ID"], env["REGION"],
                                           google_adapters.batch_config(env)),
        google_adapters.build_queue_client(env),
        google_adapters.build_clock(),
        google_adapters.build_artifact_store(env["RESULTS_BUCKET"]),
        manifests=google_adapters.build_manifest_store(env["RESULTS_BUCKET"]),
        policy=DispatchPolicy(
            budget=int(env.get("BUDGET_CENTS", "0")),
            deadline_seconds=int(env.get("DEADLINE_SECONDS", "3600")),
        ),
        prefix=env.get("RESULT_PREFIX", ""),
    )


HANDLERS = {"dispatch": handle_dispatch, "reconcile": handle_reconcile}


def main(argv=None):
    """Minimal invocation: ``entry dispatch|reconcile '<json-body>'`` for smoke tests."""
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 2 or argv[0] not in HANDLERS:
        raise SystemExit("usage: entry dispatch <json-body> | entry reconcile <json-body>")
    service = build_service()
    code, body = HANDLERS[argv[0]](service, argv[1])
    json.dump(body, sys.stdout)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
