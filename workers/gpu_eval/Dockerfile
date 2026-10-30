# Root build context contains only the public stdlib adapter. For real inference,
# override with an approved digest-pinned Python/CUDA dependency runtime. That
# runtime and the separately provisioned --launcher must not contain cloud SDKs,
# model weights or credentials; approved artifacts are fetched by launcher seams.
ARG WORKER_RUNTIME_IMAGE=python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337
FROM ${WORKER_RUNTIME_IMAGE} AS runtime
USER 0:0
ARG WORKER_RUNTIME_IMAGE
RUN python -c 'import re,sys; sys.exit(0 if re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", sys.argv[1]) else "WORKER_RUNTIME_IMAGE must be pinned by sha256 digest")' "${WORKER_RUNTIME_IMAGE}"
ENV PYTHONPATH=/app PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    HOME=/tmp HF_HUB_DISABLE_TELEMETRY=1
WORKDIR /app
COPY workers/__init__.py /app/workers/__init__.py
COPY workers/gpu_eval/__init__.py workers/gpu_eval/main.py workers/gpu_eval/manifest.py /app/workers/gpu_eval/
COPY services/lifemate_cloud /app/services/lifemate_cloud
# Reject cloud clients/auth, but allow inference dependencies such as protobuf.
RUN python -c 'import importlib.metadata as m,sys; banned=sorted(d.metadata["Name"] for d in m.distributions() if d.metadata["Name"].lower().replace("_", "-").startswith(("google-cloud-", "google-auth", "google-api-python-client"))); sys.exit("Worker runtime contains cloud SDKs: " + ", ".join(banned)) if banned else None' \
    && ! command -v gcloud && ! command -v gsutil && ! command -v bq \
    && mkdir -p /work && chown 65532:65532 /work
WORKDIR /work
USER 65532:65532
ENTRYPOINT ["python", "-m", "workers.gpu_eval.main"]
CMD []
