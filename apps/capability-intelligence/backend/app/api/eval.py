"""Eval harness — golden datasets, runs, scores

Batch 8 activates this module. Batch 0 ships a stub.
"""
from fastapi import APIRouter, Depends

from ..deps import auth_dep

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "eval", "batch": 8, "status": "stub"}
