"""Change Flags Inbox — App Flow J5 + AG-2 approval gate.

Three disposition verbs match the J5 contract:

- ``POST /api/flags/{id}/approve``    — accept the flag; resolve it.
- ``POST /api/flags/{id}/reject``     — decline the flag; reason required.
- ``POST /api/flags/{id}/defer``      — leave open with a recheck cooldown.

The legacy ``POST /api/flags/{id}/resolve`` route is kept for
back-compat; it delegates to ``approve``.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import auth_dep
from ..services import catalogue_service as svc

router = APIRouter()


class DispositionPayload(BaseModel):
    note: str | None = None


class RejectPayload(BaseModel):
    """Reject requires a non-empty rationale (App Flow J5)."""

    reason: str = Field(..., min_length=1)


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "flags", "batch": 1, "status": "active"}


@router.get("")
def list_flags(
    open_only: bool = True,
    severity: str | None = None,
    kind: str | None = None,
    _=Depends(auth_dep),
) -> list[dict]:
    """List flags for the inbox.

    Optional filters surface what the FE needs without a client-side
    pass: ``severity`` (HIGH/MEDIUM/LOW) and ``kind`` (e.g. INGEST_FAILURE,
    SCHEMA_INCOMPLETE, AI_PROPOSED_EDGE).
    """
    rows = svc.list_flags(open_only=open_only)
    if severity:
        rows = [r for r in rows if (r.get("severity") or "").upper() == severity.upper()]
    if kind:
        rows = [r for r in rows if r.get("kind") == kind]
    return rows


@router.get("/_kinds")
def list_kinds(_=Depends(auth_dep)) -> dict:
    """Distinct flag kinds + severities currently in the inbox.

    Drives the filter chips on the Change Flags page so the FE doesn't
    invent kinds the backend hasn't actually emitted.
    """
    rows = svc.list_flags(open_only=False)
    kinds: dict[str, int] = {}
    severities: dict[str, int] = {}
    for r in rows:
        k = r.get("kind") or "UNKNOWN"
        kinds[k] = kinds.get(k, 0) + 1
        s = (r.get("severity") or "").upper() or "UNKNOWN"
        severities[s] = severities.get(s, 0) + 1
    return {"kinds": kinds, "severities": severities, "total": len(rows)}


@router.post("/{flag_id}/approve")
def approve(flag_id: str, payload: DispositionPayload, user=Depends(auth_dep)) -> dict:
    flag = svc.disposition_flag(
        flag_id, by=user.email, disposition="approved", note=payload.note,
    )
    if not flag:
        raise HTTPException(404, f"flag not found: {flag_id}")
    return flag


@router.post("/{flag_id}/reject")
def reject(flag_id: str, payload: RejectPayload, user=Depends(auth_dep)) -> dict:
    flag = svc.disposition_flag(
        flag_id, by=user.email, disposition="rejected", note=payload.reason,
    )
    if not flag:
        raise HTTPException(404, f"flag not found: {flag_id}")
    return flag


@router.post("/{flag_id}/defer")
def defer(flag_id: str, payload: DispositionPayload, user=Depends(auth_dep)) -> dict:
    flag = svc.disposition_flag(
        flag_id, by=user.email, disposition="deferred", note=payload.note,
    )
    if not flag:
        raise HTTPException(404, f"flag not found: {flag_id}")
    return flag


@router.post("/{flag_id}/resolve")
def resolve(flag_id: str, payload: DispositionPayload, user=Depends(auth_dep)) -> dict:
    """Legacy alias — defaults to 'approved' disposition."""
    flag = svc.resolve_flag(flag_id, by=user.email, note=payload.note)
    if not flag:
        raise HTTPException(404, f"flag not found: {flag_id}")
    return flag
