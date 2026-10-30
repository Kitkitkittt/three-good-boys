"""The private API: IAP-authenticated, role-authorized, over the ticket-15 domain.

Endpoints are exactly the plan's §4 human surface. Machine routes
(``/internal/dispatch``, ``/internal/reconcile``) are intentionally absent: they
belong to the separate IAM-private machine service (ticket 17).

The app is built by :func:`create_app` from injected collaborators so tests drive
it without credentials, network, Firestore or Cloud Tasks.
"""
import dataclasses
import datetime

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from lifemate_cloud.errors import CloudError, Conflict, Unauthorized
from lifemate_cloud.roles import Action, Role, require
from lifemate_cloud.run import TERMINAL
from . import views
from .acceptance import AcceptanceService
from .auth import ASSERTION_HEADER, AuthError, resolve_identity
from .catalog import UnknownArtifact
from .experiments import ExperimentService

IDEMPOTENCY_HEADER = "idempotency-key"
# Roles are granted by verified email; this map is owner-managed configuration.
DEFAULT_ROLES = {}

_ACTION_STATUS = {
    Unauthorized: 403,
    AuthError: 401,
    Conflict: 409,
    UnknownArtifact: 400,
}


@dataclasses.dataclass
class ApiSettings:
    """Deployment configuration for one API instance."""

    iap_audience: str
    roles: dict = dataclasses.field(default_factory=dict)
    catalog: object = None
    new_run_id: object = None
    new_experiment_id: object = None


def create_app(*, repository, verifier, settings, enqueuer=None, now=None):
    """Build the ASGI app. ``verifier(assertion) -> claims`` is the only signing seam."""
    acceptance = AcceptanceService(
        repository=repository,
        enqueuer=enqueuer,
        new_run_id=settings.new_run_id or (lambda: __import__("uuid").uuid4().hex),
    )
    experiments = ExperimentService(
        repository=repository,
        new_experiment_id=settings.new_experiment_id
        or (lambda: "exp-" + __import__("uuid").uuid4().hex),
    )
    app = FastAPI(title="lifemate-api", docs_url=None, redoc_url=None, openapi_url=None)

    clock = now or (lambda: datetime.datetime.now(datetime.timezone.utc))

    def _now_iso():
        return clock().isoformat()

    def _identity(request):
        assertion = request.headers.get(ASSERTION_HEADER)
        return resolve_identity(
            assertion, verifier, settings.iap_audience, settings.roles, now=(now() if now else None)
        )

    def _error(exc):
        status = 500
        code = "internal_error"
        for cls, mapped in _ACTION_STATUS.items():
            if isinstance(exc, cls):
                status, code = mapped, cls.__name__.lower()
                break
        if isinstance(exc, (AuthError, Unauthorized)):
            code = "forbidden" if status == 403 else "unauthenticated"
        elif isinstance(exc, Conflict):
            code = "conflict"
        elif isinstance(exc, UnknownArtifact):
            code = "unknown_artifact"
        return JSONResponse(status_code=status, content={"code": code})

    @app.exception_handler(CloudError)
    async def _cloud_error(request, exc):  # noqa: ARG001
        return _error(exc)

    @app.exception_handler(KeyError)
    async def _missing(request, exc):  # noqa: ARG001
        return JSONResponse(status_code=404, content={"code": "not_found"})

    @app.exception_handler(ValueError)
    async def _bad_request(request, exc):  # noqa: ARG001
        return JSONResponse(status_code=400, content={"code": "bad_request"})

    @app.get("/healthz")
    def healthz():
        # Liveness only: no auth, no data, so a load balancer can probe it.
        return {"status": "ok"}

    @app.get("/api/me")
    def me(request: Request):
        identity = _identity(request)
        return {"email": identity.email, "role": Role(identity.role).value}

    @app.get("/api/models")
    def models(request: Request):
        identity = _identity(request)
        require(identity.role, Action.READ_RUN)
        return settings.catalog.approved()

    @app.post("/api/experiments", status_code=201)
    async def create_experiment(request: Request):
        """Create a real, durable experiment instance from an approved template.

        Authenticated and role-gated (``SUBMIT_RUN``). The body names an approved
        template plus an approved dataset/model; every policy and provenance value
        stays on the template. Idempotent per user like run acceptance: the same
        key and body returns the stored instance, a different body conflicts.
        """
        identity = _identity(request)
        require(identity.role, Action.SUBMIT_RUN)
        key = request.headers.get(IDEMPOTENCY_HEADER, "")
        body = await request.json()
        if not isinstance(body, dict):
            raise UnknownArtifact("request", "body must be an object")
        template_id = body.get("template_id")
        if not isinstance(template_id, str) or not template_id:
            raise UnknownArtifact("request field", "missing template_id")
        template, dataset, model, label = settings.catalog.resolve_template(template_id, body)
        instance = experiments.create(
            identity.email, identity.role, key, template, dataset, model, label, _now_iso()
        )
        resolved = settings.catalog.resolve(
            instance.experiment_id,
            {"dataset_id": dataset.id, "model_id": model.id},
            instance=instance,
        )
        return views.experiment_view(instance, resolved, template)

    def _identity_for(run_id):
        """Sanitized identity for a run, resolved from its pinned request."""
        try:
            request = repository.get_request(run_id)
        except KeyError:
            return None
        return views.identity_for(
            request,
            repository.experiment_id(run_id),
            benchmark=repository.benchmark_identity(run_id),
        )

    def _artifacts_for(run_id):
        """Verified result metadata the dispatcher persisted; never GCS contents."""
        return repository.get_artifacts(run_id)

    @app.get("/api/runs")
    def list_runs(request: Request):
        identity = _identity(request)
        require(identity.role, Action.READ_RUN)
        runs = repository.all_runs()
        if identity.role is not Role.OWNER:
            runs = [run for run in runs if run.owner == identity.email]
        return {"runs": [views.summarize(run, _identity_for(run.run_id)) for run in runs]}

    @app.post("/api/experiments/{experiment_id}/runs", status_code=202)
    async def submit_run(experiment_id: str, request: Request):
        identity = _identity(request)
        key = request.headers.get(IDEMPOTENCY_HEADER, "")
        body = await request.json()
        if not isinstance(body, dict):
            raise UnknownArtifact("request", "body must be an object")
        # A created instance carries its own pinned template; a path naming a
        # registered template directly keeps the pre-existing route working.
        instance = repository.get_experiment(experiment_id)
        resolved = settings.catalog.resolve(experiment_id, body, instance=instance)
        if instance is not None:
            template = settings.catalog.experiment(instance.template_id)
        else:
            template = settings.catalog.experiment(experiment_id)
        # The benchmark content identity is pinned from the template at acceptance
        # so a later catalog edit cannot rewrite this run's identity.
        benchmark = (template.content_hash, template.cases)
        run = acceptance.accept(
            identity.email, identity.role, key, resolved,
            expected_names=template.expected_names,
            deadline_seconds=settings.catalog.deadline_seconds,
            accepted_at=_now_iso(),
            experiment_id=experiment_id,
            benchmark=benchmark,
        )
        # Enqueue after the transaction committed; a lost enqueue is repaired by
        # the reconciler, so no dispatch failure may fail the accepted request.
        try:
            acceptance.enqueue(run.run_id)
        except Exception:  # noqa: BLE001 - the persisted intent is the contract
            pass
        return views.summarize(run, _identity_for(run.run_id))

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str, request: Request):
        identity = _identity(request)
        require(identity.role, Action.READ_RUN)
        return views.detail(
            repository.get_run(run_id),
            identity=_identity_for(run_id),
            artifacts=_artifacts_for(run_id),
        )

    @app.get("/api/runs/{run_id}/failures")
    def get_failures(run_id: str, request: Request):
        identity = _identity(request)
        require(identity.role, Action.READ_RUN)
        return views.failure_view(repository.get_run(run_id))

    @app.post("/api/runs/{run_id}/cancel")
    def cancel_run(run_id: str, request: Request):
        identity = _identity(request)
        require(identity.role, Action.CANCEL_RUN)
        run = repository.get_run(run_id)
        if run.owner != identity.email and identity.role is not Role.OWNER:
            raise Unauthorized("run belongs to another user")
        if run.state not in TERMINAL and not run.cancel_requested:
            run = repository.put_run(run.request_cancel())
        return views.summarize(run, _identity_for(run_id))

    return app
