"""Cascade preview + apply endpoints (App Flow J4).

Surfaced to the frontend via the cascade preview modal on the Subcap
Deep Dive page. ``preview`` is a GET (idempotent, read-only); ``apply``
is a POST that mutates state and requires a reason in the body.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services import cascade_service

router = APIRouter()


class ApplyRequest(BaseModel):
    to_status: str = Field("Inactive", description="Target Zennify_Status value.")
    reason: str = Field(..., min_length=1, description="Audit-trail rationale; required.")


@router.get("/preview/{sub_cap_id}")
def preview(sub_cap_id: str, to_status: str = "Inactive") -> dict:
    """Read-only enumeration of downstream rows affected by a toggle."""
    try:
        report = cascade_service.preview(sub_cap_id, to_status=to_status)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return report.to_dict()


@router.post("/apply/{sub_cap_id}")
def apply(sub_cap_id: str, body: ApplyRequest) -> dict:
    """Transactionally toggle a subcap and cascade across dependents.

    Returns the same payload as ``preview`` plus ``applied=True`` and the
    persisted ``run_id`` so the FE can link to the audit log entry.
    """
    try:
        report = cascade_service.apply(
            sub_cap_id,
            to_status=body.to_status,
            reason=body.reason,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return report.to_dict()


@router.get("/runs")
def runs(limit: int = 50) -> dict:
    """Recent cascade runs for the audit dashboard."""
    return {"runs": cascade_service.list_runs(limit=limit)}
