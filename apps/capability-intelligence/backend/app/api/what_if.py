"""What-If sandbox — counterfactual edits + impact preview (read-only)."""

from dataclasses import asdict

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..deps import auth_dep
from ..services import what_if_service

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "what_if", "batch": 8, "status": "active"}


class Action(BaseModel):
    kind: str
    target: dict = {}


class SimulateBody(BaseModel):
    actions: list[Action] = []


@router.post("/simulate")
def simulate(body: SimulateBody, _=Depends(auth_dep)) -> dict:
    raw = [a.model_dump() for a in body.actions]
    return asdict(what_if_service.simulate(raw))
