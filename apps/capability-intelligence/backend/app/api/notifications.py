"""In-app notifications fed by audit + lifecycle + suggestions."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import auth_dep
from ..services import notifications_service

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "notifications", "batch": 8, "status": "active"}


@router.get("")
def list_notifications(
    severity: str | None = Query(default=None),
    unread_only: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=1000),
    _=Depends(auth_dep),
) -> list[dict]:
    return notifications_service.list_notifications(
        severity=severity, unread_only=unread_only, limit=limit,
    )


@router.get("/stats")
def stats(_=Depends(auth_dep)) -> dict:
    return notifications_service.stats()


@router.post("/refresh")
def refresh(_=Depends(auth_dep)) -> dict:
    return asdict(notifications_service.refresh())


@router.post("/{notification_id}/read")
def mark_read(notification_id: str, _=Depends(auth_dep)) -> dict:
    rec = notifications_service.mark_read(notification_id)
    if not rec:
        raise HTTPException(status_code=404, detail="notification not found")
    return rec


@router.post("/mark-all-read")
def mark_all_read(_=Depends(auth_dep)) -> dict:
    return {"marked": notifications_service.mark_all_read()}
