"""IAM-private ASGI adapter; Google clients are constructed only by the factory."""
from fastapi import Body, FastAPI
from fastapi.responses import JSONResponse

from lifemate_cloud.errors import CloudError

from .http import handle_dispatch, handle_reconcile, status_for


def create_app(service):
    application = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @application.exception_handler(CloudError)
    async def cloud_error(request, exc):
        return JSONResponse(status_code=status_for(exc), content={"code": type(exc).__name__.lower()})

    def invoke(handler, payload):
        try:
            status, body = handler(service, payload)
        except (KeyError, TypeError, ValueError):
            return JSONResponse(status_code=400, content={"code": "bad_request"})
        return JSONResponse(status_code=status, content=body)


    @application.get("/healthz")
    def healthz():
        # Liveness only: the revision must become ready before any cloud client
        # is reachable, so this touches no service and no dependency.
        return JSONResponse(status_code=200, content={"status": "ok"})

    @application.post("/internal/dispatch")
    def dispatch(payload: dict):
        if not isinstance(payload.get("run_id"), str) or not payload["run_id"]:
            return JSONResponse(status_code=400, content={"code": "bad_request"})
        return invoke(handle_dispatch, payload)

    @application.post("/internal/reconcile")
    def reconcile(payload: dict | None = Body(default=None)):
        if payload and "run_id" in payload and (
            not isinstance(payload["run_id"], str) or not payload["run_id"]
        ):
            return JSONResponse(status_code=400, content={"code": "bad_request"})
        return invoke(handle_reconcile, payload)

    return application


def app():
    """``uvicorn dispatcher.server:app --factory --host 0.0.0.0 --port 8080``."""
    from .entry import build_service

    return create_app(build_service())
