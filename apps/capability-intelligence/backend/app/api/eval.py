"""Eval harness — golden datasets, runs, scores."""

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import auth_dep
from ..services import eval_service

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "eval", "batch": 8, "status": "active"}


@router.get("/datasets")
def datasets(_=Depends(auth_dep)) -> list[dict]:
    return eval_service.list_datasets()


@router.get("/runs")
def runs(limit: int = Query(default=50, ge=1, le=500), _=Depends(auth_dep)) -> list[dict]:
    return eval_service.list_runs(limit=limit)


@router.get("/runs/{run_id}")
def run_detail(run_id: str, _=Depends(auth_dep)) -> dict:
    rec = eval_service.get_run(run_id)
    if not rec:
        raise HTTPException(status_code=404, detail="eval run not found")
    return rec


@router.post("/run")
def run(dataset_id: str | None = Query(default=None), _=Depends(auth_dep)) -> dict:
    try:
        return eval_service.run_eval(dataset_id=dataset_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"unknown dataset: {dataset_id}")
