"""QA & Audit Dashboard API (Phase 5 — IMP-8 retrieval telemetry tile,
IMP-9 per-user budget tile, IMP-13 source-health tile).

Surfaces the read-only aggregates that the Mission Control + Settings
pages render for engineering / pillar leads. Write surface (set budget
override) is admin-gated via :func:`admin_dep`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..deps import admin_dep, auth_dep
from ..services import (
    retrieval_telemetry,
    source_health_digest,
    user_budget,
)
from ..services.eval import eval_harness
from ..services.observability import slos

router = APIRouter()


# ─── Retrieval telemetry tile (IMP-8) ───────────────────────────────────────


@router.get("/retrieval/summary")
def retrieval_summary(
    hours: int = Query(default=24, ge=1, le=24 * 7),
    user=Depends(auth_dep),
) -> dict:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    return retrieval_telemetry.summary(since=since)


@router.get("/retrieval/recent")
def retrieval_recent(
    limit: int = Query(default=50, ge=1, le=200),
    operation: str | None = Query(default=None),
    user=Depends(auth_dep),
) -> list[dict]:
    return retrieval_telemetry.list_recent(limit=limit, operation=operation)


# ─── Per-user budget tile (IMP-9) ───────────────────────────────────────────


@router.get("/budgets/me")
def my_budget(user=Depends(auth_dep)) -> dict:
    decision = user_budget.decision_for(getattr(user, "email", ""))
    return {
        "user_email": decision.user_email,
        "day": decision.day,
        "spend_usd": decision.spend_usd,
        "budget_usd": decision.budget_usd,
        "fraction": decision.fraction,
        "should_downgrade": decision.should_downgrade,
        "admin_override": decision.admin_override,
        "headroom_usd": decision.headroom_usd,
    }


@router.get("/budgets/top-spenders")
def budgets_top_spenders(
    limit: int = Query(default=25, ge=1, le=100),
    user=Depends(auth_dep),
) -> list[dict]:
    return user_budget.top_spenders(limit=limit)


@router.get("/budgets/overrides")
def budgets_overrides(user=Depends(auth_dep)) -> list[dict]:
    return user_budget.list_overrides()


class BudgetOverrideBody(BaseModel):
    user_email: str
    budget_usd: float
    reason: str | None = None


@router.post("/budgets/overrides")
def budgets_set_override(body: BudgetOverrideBody, user=Depends(admin_dep)) -> dict:
    if body.budget_usd < 0:
        raise HTTPException(status_code=400, detail="budget_usd must be ≥0")
    override = user_budget.set_user_budget_override(
        body.user_email,
        daily_budget_usd=body.budget_usd,
        set_by=user.email,
    )
    return override


@router.delete("/budgets/overrides/{user_email}")
def budgets_clear_override(user_email: str, user=Depends(admin_dep)) -> dict:
    cleared = user_budget.clear_user_budget_override(
        user_email=user_email, cleared_by=user.email
    )
    return {"cleared": cleared, "user_email": user_email}


@router.get("/budgets/audit")
def budgets_audit(
    limit: int = Query(default=100, ge=1, le=500),
    user=Depends(auth_dep),
) -> list[dict]:
    return user_budget.list_audit(limit=limit)


# ─── Source-health tile (IMP-13) ────────────────────────────────────────────


@router.get("/source-health/latest")
def source_health_latest(
    hours: int = Query(default=24, ge=1, le=24 * 30),
    user=Depends(auth_dep),
) -> dict:
    digest = source_health_digest.compose_digest(window_hours=hours)
    return {
        "digest_id": digest.digest_id,
        "window_start": digest.window_start,
        "window_end": digest.window_end,
        "n_sources_seen": digest.n_sources_seen,
        "n_flagged": digest.n_flagged,
        "by_flag": digest.by_flag,
        "rows": [
            {
                "source_id": r.source_id,
                "independence_class": r.independence_class,
                "tos_status": r.tos_status,
                "success": r.success,
                "failure": r.failure,
                "disabled": r.disabled,
                "circuit_open": r.circuit_open,
                "failure_rate": r.failure_rate,
                "last_success_at": r.last_success_at,
                "last_failure_at": r.last_failure_at,
                "days_since_success": r.days_since_success,
                "flags": r.flags,
            }
            for r in digest.rows
        ],
    }


@router.get("/source-health/digests")
def source_health_digests(
    limit: int = Query(default=14, ge=1, le=90),
    user=Depends(auth_dep),
) -> list[dict]:
    return source_health_digest.list_recent_digests(limit=limit)


@router.post("/source-health/run-now")
def source_health_run_now(user=Depends(admin_dep)) -> dict:
    return source_health_digest.send_digest()


# ─── SLO + eval harness tiles ───────────────────────────────────────────────


@router.get("/slos")
def list_slos(user=Depends(auth_dep)) -> dict:
    return {
        "slos": slos.list_slos(),
        "alert_policies": slos.render_alert_policies(),
    }


@router.get("/eval/baselines")
def eval_baselines(user=Depends(auth_dep)) -> list[dict]:
    return eval_harness.list_baselines()


@router.post("/eval/run")
def eval_run_harness(user=Depends(auth_dep)) -> dict:
    result = eval_harness.run_harness()
    return result.to_dict()
