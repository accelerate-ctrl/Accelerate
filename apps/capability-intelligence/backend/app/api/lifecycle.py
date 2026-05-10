"""Lifecycle Manager — 6-state weighted scoring, kanban

Batch 6 activates this module. Batch 0 ships a stub.
"""
from fastapi import APIRouter, Depends

from ..deps import auth_dep

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "lifecycle", "batch": 6, "status": "stub"}
