"""Lifecycle Manager — 6-state weighted scoring + state transitions."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import auth_dep
from ..services import lifecycle_service

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "lifecycle", "batch": 6, "status": "active"}


@router.get("")
def list_scores(
    state: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
    _=Depends(auth_dep),
) -> list[dict]:
    return lifecycle_service.list_scores(state=state, limit=limit)


@router.get("/states")
def state_distribution(_=Depends(auth_dep)) -> dict:
    return lifecycle_service.state_distribution()


@router.get("/transitions")
def transitions(
    sub_cap_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
    _=Depends(auth_dep),
) -> list[dict]:
    return lifecycle_service.list_transitions(sub_cap_id=sub_cap_id, limit=limit)


@router.get("/runs/latest")
def latest_run(_=Depends(auth_dep)) -> dict | None:
    return lifecycle_service.latest_run()


@router.post("/recompute")
def recompute(_=Depends(auth_dep)) -> dict:
    return asdict(lifecycle_service.recompute_all())


@router.get("/{sub_cap_id}")
def detail(sub_cap_id: str, _=Depends(auth_dep)) -> dict:
    rec = lifecycle_service.get_score(sub_cap_id)
    if not rec:
        raise HTTPException(status_code=404, detail="lifecycle score not found")
    return rec
