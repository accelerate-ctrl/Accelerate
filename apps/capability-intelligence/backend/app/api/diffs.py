"""Version diffs — generate, render, narrate

Batch 1 activates this module. Batch 0 ships a stub.
"""
from fastapi import APIRouter, Depends

from ..deps import auth_dep

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "diffs", "batch": 1, "status": "stub"}
