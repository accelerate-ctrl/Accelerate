"""Benchmarks Studio — distributions, peer cohorts, sources, adversary verdict

Batch 5 activates this module. Batch 0 ships a stub.
"""
from fastapi import APIRouter, Depends

from ..deps import auth_dep

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "benchmarks", "batch": 5, "status": "stub"}
