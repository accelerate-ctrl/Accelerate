"""7-step reasoning chain log viewer + ad-hoc loop trigger."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..deps import auth_dep
from ..services import consultant_loop
from ..services.llm.cost_tracker import BudgetExceeded
from ..services.llm.router import ModelKind

router = APIRouter()
log = logging.getLogger(__name__)


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
    """Run the 7-step consultant loop.

    Failure semantics — never returns 500:
      400  invalid model string
      422  loop raised — body includes `{error_type, stage, detail}` so the
           UI can render an actionable message instead of a blank "Lookup
           failed". Common cases: Anthropic key invalid, Vertex region
           misconfigured, repository unreachable.
      429  budget ceiling hit
    """
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
    except Exception as exc:  # noqa: BLE001 — boundary handler
        log.exception("consultant_loop.run failed (query=%r sub_cap_id=%r)",
                      body.query[:120], body.sub_cap_id)
        # Try to figure out which stage we were in. The loop logs steps as
        # it goes; in dev we read the *most recent* persisted chain even if
        # it failed mid-way so the UI can show partial progress.
        latest = consultant_loop.list_chains(
            sub_cap_id=body.sub_cap_id, limit=1
        )
        last_step = None
        if latest:
            steps = latest[0].get("steps") or []
            last_step = (steps[-1] or {}).get("name") if steps else None
        raise HTTPException(status_code=422, detail={
            "error_type": type(exc).__name__,
            "stage": last_step or "unknown",
            "detail": str(exc)[:500],
            "model_requested": body.model,
            "hint": (
                "Check /api/ready → llm.adapters for credential health. "
                "If anthropic/vertex show error, re-rotate the Secret "
                "Manager secret and redeploy."
            ),
        })
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
