# Build from the repository root. This image contains control-plane code only.
FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337 AS dependencies
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
RUN python -m venv /opt/venv
COPY services/lifemate_api/requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/python -m pip install --require-hashes -r /tmp/requirements.txt

FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337 AS runtime
ENV PATH="/opt/venv/bin:$PATH" PYTHONPATH=/app/services \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
WORKDIR /app
COPY --from=dependencies /opt/venv /opt/venv
COPY services/lifemate_cloud /app/services/lifemate_cloud
COPY services/lifemate_api /app/services/lifemate_api
COPY services/dispatcher /app/services/dispatcher
USER 65532:65532
EXPOSE 8080
# Dispatcher uses the same image with: uvicorn dispatcher.server:app --factory --host 0.0.0.0 --port 8080
CMD ["uvicorn", "lifemate_api.server:app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
