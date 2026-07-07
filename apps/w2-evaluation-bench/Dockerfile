# W2 Evaluation Bench — server image (Cloud Run).
# The image contains the deterministic brain only: FastAPI + the vendored v4.7
# engine. There is NO model client and NO credential in this image; all model
# judgment is pulled by the operator-side runner over HTTPS.
# BASE_IMAGE override lets restricted networks build from a registry mirror
# (e.g. --build-arg BASE_IMAGE=mirror.gcr.io/library/python:3.12-slim).
ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server/ server/
COPY engine/ engine/
# runner/ + examples/ are NOT executed in this container — they are the
# payload behind GET /runner.zip and /install.sh (FR-12): members' machines
# download them from the deployed service. Without these COPYs the installer
# would ship an empty runner (caught by the v2.0 QA pass).
COPY runner/ runner/
COPY examples/ examples/
# Run state lives on the mounted volume in production (see deploy script);
# /data works standalone for docker-run testing too.
ENV W2APP_DATA=/data
RUN mkdir -p /data/runs
# Cloud Run injects PORT; default 8080 for local docker run.
CMD exec python -m uvicorn server.main:app --host 0.0.0.0 --port ${PORT:-8080}
