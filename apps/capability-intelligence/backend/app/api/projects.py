"""Project–Subcap Trace — SOW + story timeline per subcap."""
from fastapi import APIRouter, Depends, HTTPException

from ..deps import auth_dep
from ..services import sow_service as svc

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "projects", "batch": 3, "status": "active"}


@router.get("/subcap-trace")
def subcap_trace(sub_cap_id: str, _=Depends(auth_dep)) -> dict:
    if not sub_cap_id:
        raise HTTPException(400, "sub_cap_id required")
    return svc.trace_for_subcap(sub_cap_id)
