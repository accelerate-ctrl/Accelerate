"""Trends monitor — emerging signals from public sources

Batch 4 activates this module. Batch 0 ships a stub.
"""
from fastapi import APIRouter, Depends

from ..deps import auth_dep

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "trends", "batch": 4, "status": "stub"}
