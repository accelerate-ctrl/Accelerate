"""Catalogue versioning — snapshot, list, get."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import auth_dep
from ..services import version_service as svc

router = APIRouter()


class SaveVersionPayload(BaseModel):
    label: str | None = None
    summary: str | None = None


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "versions", "batch": 1, "status": "active"}


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
