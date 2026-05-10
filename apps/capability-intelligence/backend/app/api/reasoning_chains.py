"""7-step reasoning chain log viewer + ad-hoc loop trigger."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..deps import auth_dep
from ..services import consultant_loop
from ..services.llm.cost_tracker import BudgetExceeded
from ..services.llm.router import ModelKind

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "reasoning_chains", "batch": 4, "status": "active"}


@router.get("")
def list_chains(
    sub_cap_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    _=Depends(auth_dep),
) -> list[dict]:
    return consultant_loop.list_chains(sub_cap_id=sub_cap_id, limit=limit)


@router.get("/{chain_id}")
def get_chain(chain_id: str, _=Depends(auth_dep)) -> dict:
    chain = consultant_loop.get_chain(chain_id)
    if not chain:
        raise HTTPException(status_code=404, detail="chain not found")
    return chain


class LoopBody(BaseModel):
    query: str
    sub_cap_id: str | None = None
    model: str = "gemini-pro"  # gemini-flash | gemini-pro | sonnet | opus


@router.post("/run")
def trigger(body: LoopBody, _=Depends(auth_dep)) -> dict:
    try:
        model = ModelKind(body.model)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"unknown model: {body.model}")
    try:
        result = consultant_loop.run(
            query=body.query,
            sub_cap_id=body.sub_cap_id,
            synth_model=model,
        )
    except BudgetExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    out = {
        "chain_id": result.chain_id,
        "sub_cap_id": result.sub_cap_id,
        "started_at": result.started_at,
        "completed_at": result.completed_at,
        "overall": result.overall,
        "total_cost_usd": result.total_cost_usd,
        "claim_count": len(result.output.get("claims", [])),
        "suggestion_count": len(result.suggestions),
        "gates_overall": result.gates.get("overall"),
    }
    return out
