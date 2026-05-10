"""Multi-lens projections of the catalogue (pillar, cluster, subvertical, maturity, lifecycle, vendor, UC tag)

Batch 2 activates this module. Batch 0 ships a stub.
"""
from fastapi import APIRouter, Depends

from ..deps import auth_dep

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "lens", "batch": 2, "status": "stub"}
