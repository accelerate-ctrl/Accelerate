"""AI-generated suggestion lifecycle — generate, stage, apply, reject

Batch 4 activates this module. Batch 0 ships a stub.
"""
from fastapi import APIRouter, Depends

from ..deps import auth_dep

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "suggestions", "batch": 4, "status": "stub"}
