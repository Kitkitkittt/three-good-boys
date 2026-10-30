# BuildKit named context approved_submission MUST be supplied from an authorized
# private workspace. It replaces the failing stage below, never repository data.
# This is a packaging interface, not an organizer-confirmed launch contract.
ARG SUBMISSION_RUNTIME_IMAGE=python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337
FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337 AS approved_submission
RUN printf '%s\n' 'Missing approved private submission artifacts. Supply --build-context approved_submission=/absolute/approved-payload; the public repository contains no runner, SDK or weights.' >&2; exit 1

FROM ${SUBMISSION_RUNTIME_IMAGE} AS dependencies
USER 0:0
ARG SUBMISSION_RUNTIME_IMAGE
ARG PRIVATE_ARTIFACTS_APPROVED=no
RUN test "${PRIVATE_ARTIFACTS_APPROVED}" = yes || { printf '%s\n' 'Private build approval is required: --build-arg PRIVATE_ARTIFACTS_APPROVED=yes' >&2; exit 1; }
RUN python -c 'import re,sys; sys.exit(0 if re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", sys.argv[1]) else "SUBMISSION_RUNTIME_IMAGE must be pinned by sha256 digest")' "${SUBMISSION_RUNTIME_IMAGE}"
RUN python -m venv --system-site-packages /opt/venv
COPY --from=approved_submission /requirements.lock /tmp/requirements.lock
RUN --network=none --mount=type=bind,from=approved_submission,source=/wheelhouse,target=/wheelhouse,ro \
    /opt/venv/bin/python -m pip install --no-index --no-cache-dir --require-hashes --find-links=/wheelhouse -r /tmp/requirements.lock

FROM ${SUBMISSION_RUNTIME_IMAGE} AS runtime
USER 0:0
ENV PATH="/opt/venv/bin:$PATH" PYTHONPATH=/opt/submission/app:/opt/submission/sdk \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 DO_NOT_TRACK=1
COPY --from=dependencies /opt/venv /opt/venv
COPY --from=approved_submission --chmod=0555 /launcher /opt/submission/launcher
COPY --from=approved_submission /app/ /opt/submission/app/
COPY --from=approved_submission /sdk/ /opt/submission/sdk/
COPY --from=approved_submission /models/ /opt/submission/models/
RUN python -c 'import importlib.metadata as m,sys; banned=sorted(d.metadata["Name"] for d in m.distributions() if d.metadata["Name"].lower().replace("_", "-").startswith(("google-cloud-", "google-auth", "google-api-python-client"))); sys.exit("Offline runtime contains cloud SDKs: " + ", ".join(banned)) if banned else None' \
    && ! command -v gcloud && ! command -v gsutil && ! command -v bq \
    && test -n "$(find /opt/submission/models -type f -print -quit)" \
    && chmod -R a+rX /opt/submission \
    && mkdir -p /work && chown 65532:65532 /work
WORKDIR /work
USER 65532:65532
# The approved executable owns its CLI and output path. No official command is
# invented here; all docker run arguments are passed to this real launcher.
ENTRYPOINT ["/opt/submission/launcher"]
CMD []
