"""Catalogue browsing — pillars / categories / L1 / subcaps / use cases / L3 / L4 / themes

Batch 1 activates this module. Batch 0 ships a stub.
"""
from fastapi import APIRouter, Depends

from ..deps import auth_dep

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "catalogue", "batch": 1, "status": "stub"}
