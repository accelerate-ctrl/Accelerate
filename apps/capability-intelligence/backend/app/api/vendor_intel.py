"""Vendor Intelligence — adoption per cohort, news events, heatmap."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import auth_dep
from ..services import vendor_intel_service

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "vendor_intel", "batch": 6, "status": "active"}


@router.post("/refresh")
def refresh(_=Depends(auth_dep)) -> dict:
    return asdict(vendor_intel_service.refresh())


@router.get("/vendors")
def list_vendors(
    category: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    _=Depends(auth_dep),
) -> list[dict]:
    return vendor_intel_service.list_vendors(category=category, limit=limit)


@router.get("/vendors/{vendor_id}")
def detail(vendor_id: str, _=Depends(auth_dep)) -> dict:
    rec = vendor_intel_service.get_vendor(vendor_id)
    if not rec:
        raise HTTPException(status_code=404, detail="vendor not found")
    return rec


@router.get("/adoption")
def adoption(
    vendor_id: str | None = Query(default=None),
    cohort_id: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
    _=Depends(auth_dep),
) -> list[dict]:
    return vendor_intel_service.list_adoption(
        vendor_id=vendor_id, cohort_id=cohort_id, limit=limit,
    )


@router.get("/heatmap")
def heatmap(_=Depends(auth_dep)) -> dict:
    return vendor_intel_service.heatmap()


@router.get("/events")
def events(
    vendor_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    _=Depends(auth_dep),
) -> list[dict]:
    return vendor_intel_service.list_events(vendor_id=vendor_id, limit=limit)


@router.get("/runs/latest")
def latest_run(_=Depends(auth_dep)) -> dict | None:
    return vendor_intel_service.latest_run()
