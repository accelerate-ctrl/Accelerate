"""News + trends watch — local seed (dev) / RSS (live) + impact synthesis."""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..deps import auth_dep
from ..services import news_service, trends_service
from ..services.repository import get_repository

router = APIRouter()


@router.get("")
def list_news(
    sub_cap_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    _=Depends(auth_dep),
) -> list[dict]:
    return news_service.list_news(limit=limit, sub_cap_id=sub_cap_id)


@router.post("/refresh")
def refresh(_=Depends(auth_dep)) -> dict:
    return news_service.refresh().__dict__


@router.post("/impact-synthesise")
def impact_synthesise(
    limit: int = Query(default=50, ge=1, le=200),
    force: bool = Query(default=False, description="re-synth items that already have impact"),
    _=Depends(auth_dep),
) -> dict:
    """On-demand impact pass. Runs Gemini Flash on up to `limit` items
    missing an impact block (or all of them if `force=True`)."""
    return news_service.synthesise_impact_batch(limit=limit, force=force)


class ProposeChangeBody(BaseModel):
    reason: str | None = None


@router.post("/{news_id}/propose-change")
def propose_change(news_id: str, body: ProposeChangeBody, user=Depends(auth_dep)) -> dict:
    """Create a Suggestion of kind `news_proposed` from a news item's
    impact block. Operator can then review / Apply / Reject from the AI
    Suggestions board or the QA Audit dashboard."""
    repo = get_repository()
    news = repo.get("news_items", news_id)
    if not news:
        raise HTTPException(404, f"news item not found: {news_id}")
    impact = news.get("impact") or {}
    if not impact.get("impact_class"):
        raise HTTPException(409, "news item has no impact block — run impact-synthesise first")

    # Build a suggestion record matching the existing `suggestions` schema.
    sid = f"sug-{uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    # Pick the strongest target subcap (first affected) or the suggested
    # new-subcap candidate's L1 if the class is catalogue_extension.
    target = (impact.get("affects_subcaps") or [None])[0]
    if impact.get("impact_class") == "catalogue_extension" and isinstance(
        impact.get("suggests_new_subcap"), dict
    ):
        target = target or impact["suggests_new_subcap"].get("candidate_l1")

    title_root = (impact.get("summary") or news.get("title") or "news-proposed change").strip()
    rationale_bits = [
        f"From news: {news.get('title')}",
        f"Source: {news.get('url') or news.get('source') or '?'}",
        f"Class: {impact.get('impact_class')}",
        f"Confidence: {impact.get('confidence')}",
    ]
    if body.reason:
        rationale_bits.append(f"Operator note: {body.reason}")

    record = {
        "id": sid,
        "kind": "news_proposed",
        "origin": "news",
        "target": target,
        "title": title_root[:160],
        "rationale": "\n".join(rationale_bits),
        "status": "pending",
        "chain_id": None,
        "gate_overall": "n/a",
        "created_at": now,
        "created_by": user.email,
        "source_refs": {
            "news_id": news_id,
            "impact": impact,
        },
    }
    repo.upsert("suggestions", sid, record)
    return {"suggestion_id": sid, "status": "pending", "target": target}


@router.get("/runs/latest")
def latest_run(_=Depends(auth_dep)) -> dict | None:
    return news_service.latest_run()


@router.get("/trends")
def list_trends(limit: int = Query(default=50, ge=1, le=200), _=Depends(auth_dep)) -> list[dict]:
    return trends_service.list_clusters(limit=limit)


@router.post("/trends/recompute")
def trends_recompute(
    k: int = Query(default=8, ge=2, le=20),
    lookback_days: int = Query(default=30, ge=1, le=180),
    _=Depends(auth_dep),
) -> dict:
    return trends_service.recompute_clusters(k=k, lookback_days=lookback_days)


@router.get("/trends/{cluster_id}")
def get_trend(cluster_id: str, _=Depends(auth_dep)) -> dict:
    cluster = trends_service.get_cluster(cluster_id)
    if not cluster:
        raise HTTPException(404, f"trend cluster not found: {cluster_id}")
    # Hydrate members
    repo = get_repository()
    members = []
    for mid in cluster.get("member_ids") or []:
        item = repo.get("news_items", mid)
        if item:
            members.append(item)
    return {**cluster, "members": members}


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "news", "batch": 4, "status": "active"}
