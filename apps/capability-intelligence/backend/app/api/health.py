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
    # LLM adapter probe — surfaces credential health at a glance. Probe is
    # wrapped in try/except so a misconfigured Vertex/Anthropic key can't
    # make /api/ready 5xx (Cloud Run uses this for readiness).
    try:
        from ..services.llm import router as llm_router
        llm_block: dict = llm_router.probe()
    except Exception as exc:  # noqa: BLE001
        llm_block = {"probe_error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    return {
        "status": "ready",
        "env": settings.env,
        "auth_mode": settings.auth_mode,
        "use_gcp": settings.use_gcp,
        "project": settings.gcp_project_id,
        "region": settings.gcp_region,
        "service": os.getenv("K_SERVICE") or settings.cloud_run_service,
        "revision": os.getenv("K_REVISION") or settings.cloud_run_revision,
        "llm": {"adapters": llm_block},
    }
