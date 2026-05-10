"""Liveness + readiness probes."""
from fastapi import APIRouter

from ..config import get_settings

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}


@router.get("/ready")
def ready() -> dict:
    settings = get_settings()
    # In Batch 1+ we'll ping Firestore here. For Batch 0 readiness == liveness.
    return {
        "status": "ready",
        "env": settings.env,
        "auth_mode": settings.auth_mode,
        "use_gcp": settings.use_gcp,
    }
