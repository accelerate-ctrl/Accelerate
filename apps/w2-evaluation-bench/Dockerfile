# W2 Evaluation Bench — server image (Cloud Run).
# The image contains the deterministic brain only: FastAPI + the vendored v4.6
# engine. There is NO model client and NO credential in this image; all model
# judgment is pulled by the operator-side runner over HTTPS.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server/ server/
COPY engine/ engine/
# Run state lives on the mounted volume in production (see deploy script);
# /data works standalone for docker-run testing too.
ENV W2APP_DATA=/data
RUN mkdir -p /data/runs
# Cloud Run injects PORT; default 8080 for local docker run.
CMD exec python -m uvicorn server.main:app --host 0.0.0.0 --port ${PORT:-8080}
