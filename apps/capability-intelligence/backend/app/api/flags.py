"""Change flags inbox."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import auth_dep
from ..services import catalogue_service as svc

router = APIRouter()


class ResolvePayload(BaseModel):
    note: str | None = None


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "flags", "batch": 1, "status": "active"}


@router.get("")
def list_flags(open_only: bool = True, _=Depends(auth_dep)) -> list[dict]:
    return svc.list_flags(open_only=open_only)


@router.post("/{flag_id}/resolve")
def resolve(flag_id: str, payload: ResolvePayload, user=Depends(auth_dep)) -> dict:
    flag = svc.resolve_flag(flag_id, by=user.email, note=payload.note)
    if not flag:
        raise HTTPException(404, f"flag not found: {flag_id}")
    return flag
