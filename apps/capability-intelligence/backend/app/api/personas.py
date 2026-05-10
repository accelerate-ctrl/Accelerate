"""Persona-overlaid views — personas drawn from subcap.personas."""

from fastapi import APIRouter, Depends, HTTPException

from ..deps import auth_dep
from ..services import personas_service

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "personas", "batch": 8, "status": "active"}


@router.get("")
def list_personas(limit: int = 200, _=Depends(auth_dep)) -> list[dict]:
    return personas_service.list_personas(limit=limit)


@router.get("/{name}")
def detail(name: str, limit: int = 200, _=Depends(auth_dep)) -> dict:
    rec = personas_service.get_persona_view(name, limit=limit)
    if not rec:
        raise HTTPException(status_code=404, detail="persona not found")
    return rec
