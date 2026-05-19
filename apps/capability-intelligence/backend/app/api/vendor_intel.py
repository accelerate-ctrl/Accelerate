"""Partner Intelligence — adoption per cohort, news events, heatmap +
release-notes scan (Batch 3)."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import auth_dep
from ..services import partner_intel_service, vendor_intel_service

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
    """Legacy vendor × cohort technographic adoption heatmap."""
    return vendor_intel_service.heatmap()


@router.get("/subcap-evidence")
def subcap_evidence(_=Depends(auth_dep)) -> dict:
    """Evidence-driven vendor × subcap heatmap (Phase 2.3).

    Derived from vendor_events joined to news_items.impact
    .affected_subcaps. Each cell carries the highest magnitude seen
    across all matching events, total event count, and latest event
    timestamp.
    """
    return vendor_intel_service.subcap_evidence_heatmap()


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


# ─── Partner release-notes scan (Batch 3) ──────────────────────────────────


@router.get("/partners")
def partners(_=Depends(auth_dep)) -> list[dict]:
    """Static partner registry from config/partners.yml."""
    return [
        {
            "code": p.code, "name": p.name, "category": p.category,
            "release_notes": p.release_notes, "rss_url": p.rss_url,
            "lookback_days": p.lookback_days,
        }
        for p in partner_intel_service.load_partners()
    ]


@router.get("/releases")
def releases(
    partner_code: str | None = Query(default=None),
    days: int | None = Query(default=None, ge=1, le=365),
    limit: int = Query(default=200, ge=1, le=1000),
    _=Depends(auth_dep),
) -> list[dict]:
    return partner_intel_service.list_releases(
        partner_code=partner_code, days=days, limit=limit,
    )


@router.get("/catalogue-gaps")
def catalogue_gaps(_=Depends(auth_dep)) -> list[dict]:
    """High-confidence features the partners shipped that the catalogue
    doesn't yet reflect. Grouped by mapped L1 capability."""
    return partner_intel_service.catalogue_gaps()


@router.post("/scan-releases")
def scan_releases(
    limit_per_partner: int = Query(default=25, ge=1, le=100),
    _=Depends(auth_dep),
) -> dict:
    """On-demand re-run of the partner-release-notes scan. Same code
    path as the daily Cloud Run Job, so the operator can re-trigger
    after pushing a config change."""
    return partner_intel_service.run_scan(limit_per_partner=limit_per_partner)


@router.get("/partner-runs/latest")
def partner_latest_run(_=Depends(auth_dep)) -> dict | None:
    return partner_intel_service.latest_run()
