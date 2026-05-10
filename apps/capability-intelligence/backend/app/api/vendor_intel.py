"""Vendor Intelligence — events, heatmaps, win/loss

Batch 6 activates this module. Batch 0 ships a stub.
"""
from fastapi import APIRouter, Depends

from ..deps import auth_dep

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "vendor_intel", "batch": 6, "status": "stub"}
