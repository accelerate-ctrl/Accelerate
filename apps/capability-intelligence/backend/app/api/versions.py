"""Catalogue versioning — snapshot, list, get, revert."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import admin_dep, auth_dep
from ..services import version_service as svc

router = APIRouter()


class SaveVersionPayload(BaseModel):
    label: str | None = None
    summary: str | None = None


class RevertPayload(BaseModel):
    """J11 admin-gated revert. Reason required for the audit trail."""
    reason: str = Field(..., min_length=1)


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "versions", "batch": 1, "status": "active"}


@router.get("/_reverts")
def list_reverts(limit: int = 50, _=Depends(auth_dep)) -> dict:
    """Recent revert events for the audit dashboard.

    Declared BEFORE the parametric ``/{version_id}`` route so FastAPI
    doesn't treat ``_reverts`` as a version id.
    """
    return {"reverts": svc.list_reverts(limit=limit)}


@router.get("")
def list_versions(limit: int = 50, _=Depends(auth_dep)) -> list[dict]:
    return svc.list_versions(limit=limit)


@router.post("")
def save_version(payload: SaveVersionPayload, user=Depends(auth_dep)) -> dict:
    return svc.save_version(label=payload.label, summary=payload.summary, by=user.email)


@router.get("/{version_id}")
def get_version(version_id: str, _=Depends(auth_dep)) -> dict:
    v = svc.get_version(version_id)
    if not v:
        raise HTTPException(404, f"version not found: {version_id}")
    return v


@router.get("/{version_id}/snapshot")
def get_snapshot(version_id: str, _=Depends(auth_dep)) -> dict:
    snap = svc.load_snapshot(version_id)
    if not snap:
        raise HTTPException(404, f"snapshot not found for version: {version_id}")
    return snap


@router.get("/{version_id}/revert-preview")
def preview_revert(version_id: str, _=Depends(auth_dep)) -> dict:
    """J11 — what would change if we reverted to ``version_id``.

    Read-only; available to any authenticated user so pillar leads
    can review impact before requesting an admin revert.
    """
    try:
        return svc.preview_revert(version_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/{version_id}/revert")
def revert(version_id: str, body: RevertPayload, user=Depends(admin_dep)) -> dict:
    """J11 — admin-only revert. Transactional; logs the operator + reason."""
    try:
        return svc.revert_to_version(
            version_id, by=user.email, reason=body.reason,
        )
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
