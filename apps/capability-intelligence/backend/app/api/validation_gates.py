"""Validation gate dashboard — recent runs + per-gate aggregates."""

from collections import Counter

from fastapi import APIRouter, Depends, Query

from ..deps import auth_dep
from ..services import consultant_loop
from ..services.llm.cost_tracker import CostTracker

router = APIRouter()
_tracker = CostTracker()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "validation_gates", "batch": 4, "status": "active"}


@router.get("/runs")
def runs(
    limit: int = Query(default=50, ge=1, le=500),
    sub_cap_id: str | None = Query(default=None),
    _=Depends(auth_dep),
) -> list[dict]:
    """Most-recent gate runs (one per chain)."""
    chains = consultant_loop.list_chains(sub_cap_id=sub_cap_id, limit=limit)
    return [
        {
            "chain_id": c["chain_id"],
            "sub_cap_id": c.get("sub_cap_id"),
            "completed_at": c.get("completed_at"),
            "overall": c.get("overall"),
            "score": c.get("gates", {}).get("score"),
            "results": c.get("gates", {}).get("results", []),
        }
        for c in chains
    ]


@router.get("/summary")
def summary(_=Depends(auth_dep)) -> dict:
    chains = consultant_loop.list_chains(limit=500)
    overall_counts: Counter[str] = Counter(c.get("overall", "?") for c in chains)
    by_gate: dict[str, Counter] = {}
    for c in chains:
        for r in c.get("gates", {}).get("results", []):
            by_gate.setdefault(r["name"], Counter())[r["verdict"]] += 1
    return {
        "total_runs": len(chains),
        "overall": dict(overall_counts),
        "by_gate": {k: dict(v) for k, v in by_gate.items()},
        "cost_summary": _tracker.summary().__dict__,
    }
