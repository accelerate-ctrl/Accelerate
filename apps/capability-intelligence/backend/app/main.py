"""FastAPI factory + static SPA mount.

Cloud Run notes:
  * ``$PORT`` is injected by the runtime — uvicorn reads it via the launcher
    in Dockerfile (``uvicorn ... --port ${PORT:-8080}``).
  * ``K_SERVICE`` / ``K_REVISION`` are injected automatically — they're
    echoed into every startup log line so Cloud Logging traces are coherent.
  * Health probes (``/api/health`` liveness, ``/api/ready`` readiness) are
    public — they're how Cloud Run decides when to send traffic.
"""
import os
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import api_router
from .config import get_settings
from .observability import install_telemetry

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)

logger = structlog.get_logger()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Zennify Capability Intelligence",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api")

    # OpenTelemetry — only attaches when OTEL_EXPORTER_OTLP_ENDPOINT is set
    # in the environment. In dev / tests it's a no-op.
    install_telemetry(app)

    # Serve the built SPA if present (Docker image bundles it at /app/static
    # via Dockerfile; in local dev, copy frontend/dist → backend/static).
    static_dir = Path(__file__).resolve().parents[1] / "static"
    if static_dir.exists():
        assets_dir = static_dir / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
        async def spa_fallback(full_path: str) -> FileResponse:
            # Anything not matched by /api falls through to index.html (SPA
            # routing). HEAD is included because Cloud Run's HTTP/2 frontend,
            # GCLB health probes, and many uptime monitors issue HEAD requests
            # against the root path.
            index = static_dir / "index.html"
            return FileResponse(index)

    logger.info(
        "app.created",
        env=settings.env,
        auth_mode=settings.auth_mode,
        project=settings.gcp_project_id,
        region=settings.gcp_region,
        service=os.getenv("K_SERVICE") or settings.cloud_run_service,
        revision=os.getenv("K_REVISION") or settings.cloud_run_revision,
    )
    return app


app = create_app()
