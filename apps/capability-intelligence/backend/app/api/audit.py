"""Deep-audit results — sweeps + per-finding severity log."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import auth_dep
from ..services import audit_service

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "audit", "batch": 7, "status": "active"}


@router.get("")
def list_reports(
    limit: int = Query(default=50, ge=1, le=500),
    _=Depends(auth_dep),
) -> list[dict]:
    return audit_service.list_reports(limit=limit)


@router.post("/run")
def run(_=Depends(auth_dep)) -> dict:
    return asdict(audit_service.run_audit())


@router.get("/latest")
def latest(_=Depends(auth_dep)) -> dict | None:
    return audit_service.latest_report()


@router.get("/{report_id}")
def detail(report_id: str, _=Depends(auth_dep)) -> dict:
    rec = audit_service.get_report(report_id)
    if not rec:
        raise HTTPException(status_code=404, detail="audit report not found")
    return rec
