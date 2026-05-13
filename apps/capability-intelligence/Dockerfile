# syntax=docker/dockerfile:1.7
# Multi-stage build: Node builds the SPA, Python serves both /api and the bundled SPA.
#
# Cloud Run:
#   * $PORT is provided by the runtime (defaults to 8080).
#   * The container must respond on $PORT within the startup-probe window.
#   * Concurrency is set via containerConcurrency in infra/service.yaml
#     (default 80); we run a single uvicorn worker per instance because
#     Cloud Run autoscales by instance.

# ─── Stage 1: frontend build ────────────────────────────────────────────────
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ─── Stage 2: python runtime ────────────────────────────────────────────────
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

# tini = correct PID-1 signal handling for SIGTERM (Cloud Run sends it on
# scale-in). curl = readiness probe + ad-hoc debugging.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tini curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ /app/
COPY config/ /app/config/
COPY --from=web /web/dist /app/static

# Drop to a non-root user for least privilege.
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

EXPOSE 8080

# Shell-form CMD so ${PORT} is expanded at container start.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1 --proxy-headers --forwarded-allow-ips=*"]
