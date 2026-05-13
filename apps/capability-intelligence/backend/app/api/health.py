"""Liveness + readiness probes."""
import os

from fastapi import APIRouter

from ..config import get_settings

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}


@router.get("/ready")
def ready() -> dict:
    settings = get_settings()
    return {
        "status": "ready",
        "env": settings.env,
        "auth_mode": settings.auth_mode,
        "use_gcp": settings.use_gcp,
        "project": settings.gcp_project_id,
        "region": settings.gcp_region,
        "service": os.getenv("K_SERVICE") or settings.cloud_run_service,
        "revision": os.getenv("K_REVISION") or settings.cloud_run_revision,
    }
