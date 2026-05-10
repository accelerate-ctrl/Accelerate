"""Project–Subcap Trace — SOW/story → subcap mention timeline

Batch 3 activates this module. Batch 0 ships a stub.
"""
from fastapi import APIRouter, Depends

from ..deps import auth_dep

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "projects", "batch": 3, "status": "stub"}
