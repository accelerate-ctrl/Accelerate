"""Benchmarks Studio — distributions, peer cohorts, sources, adversary verdict."""

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import auth_dep
from ..services import benchmarks_service

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "benchmarks", "batch": 5, "status": "active"}


@router.get("")
def list_distributions(
    metric_id: str | None = Query(default=None),
    cohort_id: str | None = Query(default=None),
    sub_cap_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    _=Depends(auth_dep),
) -> list[dict]:
    return benchmarks_service.list_distributions(
        metric_id=metric_id, cohort_id=cohort_id, sub_cap_id=sub_cap_id, limit=limit,
    )


@router.get("/metrics")
def metrics(_=Depends(auth_dep)) -> list[dict]:
    return benchmarks_service.list_metrics()


@router.get("/cohorts")
def cohorts(_=Depends(auth_dep)) -> list[dict]:
    return benchmarks_service.list_cohorts()


@router.get("/sources")
def sources(_=Depends(auth_dep)) -> list[dict]:
    return benchmarks_service.list_sources()


@router.get("/observations")
def observations(
    metric_id: str | None = Query(default=None),
    cohort_id: str | None = Query(default=None),
    company: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
    _=Depends(auth_dep),
) -> list[dict]:
    return benchmarks_service.list_observations(
        metric_id=metric_id, cohort_id=cohort_id, company=company, limit=limit,
    )


@router.get("/runs/latest")
def latest_run(_=Depends(auth_dep)) -> dict | None:
    return benchmarks_service.latest_run()


@router.get("/{dist_id}")
def detail(dist_id: str, _=Depends(auth_dep)) -> dict:
    dist = benchmarks_service.get_distribution(dist_id)
    if not dist:
        raise HTTPException(status_code=404, detail="distribution not found")
    return dist


@router.post("/refresh")
def refresh(extrapolate: bool = Query(default=True), _=Depends(auth_dep)) -> dict:
    summary = benchmarks_service.refresh(extrapolate=extrapolate)
    return summary.__dict__
