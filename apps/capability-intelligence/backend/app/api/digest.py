"""Quarterly Strategic Digest — generate, browse, export

Batch 7 activates this module. Batch 0 ships a stub.
"""
from fastapi import APIRouter, Depends

from ..deps import auth_dep

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "digest", "batch": 7, "status": "stub"}
