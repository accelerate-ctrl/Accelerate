"""Quarterly Strategic Digest — Claude Opus narratives over the synthesis layer.

Per spec §11 / ARCHITECTURE Batch 7.

Pipeline
========

    1. Pick (subvertical, period)              ─────────────────────────┐
    2. Pull top 3-5 priorities from Batch 6                              │
       lifecycle_scores (RISING / STABLE / EMERGING)                     │
       intersected with the subvertical's subcaps via                    │
       Batch 2 vc_mappings.                                              │
    3. For each priority assemble evidence:                              │
         - SOW excerpts (Batch 3)                                        │
         - benchmark distribution (Batch 5)                              │
         - news + trends mentions (Batch 4)                              │
         - vendor stack (Batch 6)                                        │
    4. Call consultant_loop with ModelKind.OPUS to produce a             │
       narrative paragraph + recommendation per priority.                │
       (Dev mode: deterministic canned narrative.)                       │
    5. Compute Q-over-Q deltas vs the previous digest for the same       │
       (subvertical, period_minus_one).                                  │
    6. Persist strategic_digests row keyed by                            │
       digest-{subvertical}-{period} ───────────────────────────────────┘

The PPTX export module reads the persisted digest and emits a
Zennify-branded deck.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from .repository import get_repository

logger = logging.getLogger(__name__)

DIGEST_COLLECTION = "strategic_digests"
DIGEST_RUNS_COLLECTION = "digest_runs"

DEFAULT_PRIORITY_LIMIT = 5
DEFAULT_RECOMMENDED_STATES = ("RISING", "STABLE", "EMERGING")


@dataclass
class PriorityNarrative:
    sub_cap_id: str
    sub_cap_name: str
    state: str | None
    score: float | None
    confidence: float | None
    narrative: str
    recommendation: str
    evidence_sows: list[dict] = field(default_factory=list)
    evidence_benchmarks: list[dict] = field(default_factory=list)
    evidence_news: list[dict] = field(default_factory=list)
    delta: dict[str, Any] | None = None  # vs previous digest
    chain_id: str | None = None  # consultant loop trace
    cost_usd: float = 0.0


@dataclass
class StrategicDigest:
    digest_id: str
    subvertical: str
    period: str            # e.g. "2026-Q2"
    previous_period: str | None
    generated_at: str
    model: str             # which LLM produced narratives
    priorities: list[dict]
    summary: str           # the executive overview paragraph
    sources_count: int
    total_cost_usd: float


# ─── Helpers ────────────────────────────────────────────────────────────────


def _previous_period(period: str) -> str | None:
    """`2026-Q2` → `2026-Q1`; `2026-Q1` → `2025-Q4`."""
    if not period or len(period) != 7 or period[4] != "-" or period[5] != "Q":
        return None
    year = int(period[:4])
    q = int(period[6])
    if q > 1:
        return f"{year}-Q{q - 1}"
    return f"{year - 1}-Q4"


def _resolve_subvertical_codes(subvertical: str) -> set[str]:
    """Map a user-facing subvertical label to the canonical code(s).

    Accepts the canonical code (e.g. "RB"), the friendly slug ("retail-banking"),
    or the human name ("Retail Banking"). Returns a set of matching short codes
    from config/subverticals.yml.
    """
    import yaml
    from pathlib import Path

    needle = subvertical.lower().replace("-", " ").strip()
    candidates: set[str] = set()
    for parent in [Path.cwd(), *Path.cwd().parents]:
        cfg = parent / "config" / "subverticals.yml"
        if cfg.exists():
            try:
                data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
            except Exception:
                data = {}
            for sv in data.get("subverticals", []) or []:
                code = (sv.get("code") or "").lower()
                name = (sv.get("name") or "").lower()
                aliases = [a.lower() for a in (sv.get("column_aliases") or [])]
                if needle == code or needle == name or needle in aliases:
                    candidates.add(sv["code"])
            break
    # Direct code match (e.g. user passes "RB" → codes={"RB"})
    if not candidates and len(subvertical) <= 5:
        candidates.add(subvertical.upper())
    return candidates


def _filter_subcaps_for_subvertical(subvertical: str) -> set[str]:
    """Use Batch 2 vc_mappings to find subcaps relevant to a subvertical.

    Each vc_mappings row carries `sub_cap_id` + `subvertical_code` + `stages`.
    Any non-empty stages list for the chosen subvertical counts as relevance.
    """
    repo = get_repository()
    rows = repo.list("vc_mappings")
    if not rows:
        return set()  # caller handles fallback
    codes = _resolve_subvertical_codes(subvertical)
    out: set[str] = set()
    for row in rows:
        if row.get("subvertical_code") in codes and (row.get("stages") or []):
            sid = row.get("sub_cap_id")
            if sid:
                out.add(sid)
    return out


def _evidence_sow(sub_cap_id: str, *, limit: int = 3) -> list[dict]:
    repo = get_repository()
    sows_by_id = {s.get("sow_id"): s for s in repo.list("sows")}
    out: list[dict] = []
    for m in repo.list("sow_mentions"):
        if m.get("sub_cap_id") != sub_cap_id:
            continue
        sow = sows_by_id.get(m.get("sow_id"), {})
        out.append({
            "sow_id": m.get("sow_id"),
            "client": sow.get("client_name"),
            "status": sow.get("status"),
            "excerpt": (m.get("excerpt") or "")[:280],
            "method": m.get("method"),
            "confidence": m.get("confidence"),
        })
        if len(out) >= limit:
            break
    return out


def _evidence_benchmarks(sub_cap_id: str, *, limit: int = 3) -> list[dict]:
    """Pull distributions whose metric maps to this sub_cap_id."""
    from .benchmarks_service import _load_metrics

    metrics = _load_metrics()
    eligible_metric_ids = {
        m["metric_id"] for m in metrics
        if any(_pattern_match(p, sub_cap_id) for p in (m.get("subcap_mappings") or []))
    }
    repo = get_repository()
    out: list[dict] = []
    for d in repo.list("benchmark_distributions"):
        if d.get("metric_id") not in eligible_metric_ids:
            continue
        out.append({
            "metric_id": d["metric_id"],
            "cohort_id": d["cohort_id"],
            "period": d.get("period"),
            "verdict": d.get("verdict"),
            "n": d.get("n"),
            "p50": d.get("p50"),
            "p25": d.get("p25"),
            "p75": d.get("p75"),
        })
        if len(out) >= limit:
            break
    return out


def _evidence_news(sub_cap_id: str, *, limit: int = 3) -> list[dict]:
    repo = get_repository()
    out: list[dict] = []
    for collection in ("news_items", "trends_items"):
        for item in repo.list(collection):
            if sub_cap_id in (item.get("sub_cap_hits") or []):
                out.append({
                    "id": item.get("id"),
                    "title": item.get("title"),
                    "source": item.get("source"),
                    "published_at": item.get("published_at"),
                    "url": item.get("url"),
                    "kind": item.get("kind", collection.replace("_items", "")),
                })
            if len(out) >= limit:
                break
        if len(out) >= limit:
            break
    return out


def _pattern_match(pattern: str, sub_cap_id: str) -> bool:
    if pattern.endswith("*"):
        return sub_cap_id.startswith(pattern[:-1])
    return pattern == sub_cap_id


def _load_top_priorities(
    *,
    subvertical: str,
    limit: int,
    accept_states: tuple[str, ...],
) -> list[dict]:
    repo = get_repository()
    scored = list(repo.list("lifecycle_scores"))
    if not scored:
        return []
    has_mappings = bool(repo.list("vc_mappings"))
    sub_filter = _filter_subcaps_for_subvertical(subvertical)
    if has_mappings:
        # vc_mappings collection populated → filter is authoritative even if empty
        scored = [s for s in scored if s["sub_cap_id"] in sub_filter]
    elif sub_filter:
        scored = [s for s in scored if s["sub_cap_id"] in sub_filter]
    scored = [s for s in scored if s.get("state") in accept_states]
    scored.sort(key=lambda s: -float(s.get("score") or 0))
    return scored[:limit]


def _delta_vs_previous(
    sub_cap_id: str, *, subvertical: str, previous_period: str | None,
) -> dict[str, Any] | None:
    if not previous_period:
        return None
    prev = get_repository().get(
        DIGEST_COLLECTION, _digest_id(subvertical, previous_period),
    )
    if not prev:
        return None
    for p in prev.get("priorities", []):
        if p.get("sub_cap_id") == sub_cap_id:
            return {
                "previous_state": p.get("state"),
                "previous_score": p.get("score"),
                "previous_period": previous_period,
            }
    return {"previous_period": previous_period, "previous_state": None}


def _digest_id(subvertical: str, period: str) -> str:
    slug = subvertical.lower().replace(" ", "-").replace("/", "-")
    return f"digest-{slug}-{period}"


# ─── Narrative production ───────────────────────────────────────────────────


def _produce_narrative(priority: dict, sources_blob: str) -> tuple[str, str, str | None, float]:
    """Run the Batch-4 consultant loop on Opus to produce narrative + recommendation.

    Returns (narrative, recommendation, chain_id, cost_usd).  Dev-mode resolves
    to a deterministic canned narrative (so digest tests don't need creds).
    """
    from .consultant_loop import run as run_loop  # cycle-safe late import
    from .llm.router import ModelKind

    sub_cap_id = priority["sub_cap_id"]
    sub_cap_name = priority.get("sub_cap_name") or sub_cap_id
    state = priority.get("state") or "UNKNOWN"
    score = priority.get("score") or 0
    query = (
        f"Synthesize a strategic-digest narrative for {sub_cap_name} ({sub_cap_id}). "
        f"Current lifecycle state: {state}; score: {score}. "
        f"Cite the evidence and recommend a next action for the consulting team. "
        f"Evidence:\n{sources_blob}"
    )
    try:
        loop = run_loop(query=query, sub_cap_id=sub_cap_id, synth_model=ModelKind.OPUS)
    except Exception as exc:  # noqa: BLE001
        logger.warning("opus narrative failed for %s: %s", sub_cap_id, exc)
        return (
            f"{sub_cap_name} is currently {state} with score {score}. "
            "Narrative production failed — falling back to status summary.",
            "Re-run digest after addressing the upstream error.",
            None,
            0.0,
        )

    claims = loop.output.get("claims") or []
    if claims:
        narrative = " ".join(c.get("text", "") for c in claims[:2]).strip()
    else:
        narrative = (
            f"{sub_cap_name} sits at lifecycle state {state} (score {score}); "
            f"evidence above shows a coherent demand signal across the subvertical."
        )
    recommendation = (
        loop.suggestions[0].get("rationale") if loop.suggestions else
        f"Schedule a review of {sub_cap_name} in next quarter's planning cycle."
    )
    return narrative, recommendation, loop.chain_id, loop.total_cost_usd


# ─── Public API ─────────────────────────────────────────────────────────────


def generate(
    *,
    subvertical: str,
    period: str,
    priority_limit: int = DEFAULT_PRIORITY_LIMIT,
    accept_states: tuple[str, ...] = DEFAULT_RECOMMENDED_STATES,
    persist: bool = True,
) -> StrategicDigest:
    repo = get_repository()
    started = datetime.now(timezone.utc)

    with repo.defer_persist():
        return _generate_inner(
            subvertical=subvertical,
            period=period,
            priority_limit=priority_limit,
            accept_states=accept_states,
            persist=persist,
            started=started,
        )


def _generate_inner(
    *,
    subvertical: str,
    period: str,
    priority_limit: int,
    accept_states: tuple[str, ...],
    persist: bool,
    started: datetime,
) -> StrategicDigest:
    repo = get_repository()
    previous = _previous_period(period)
    top = _load_top_priorities(
        subvertical=subvertical, limit=priority_limit, accept_states=accept_states,
    )

    priorities: list[PriorityNarrative] = []
    total_cost = 0.0
    sources_count = 0

    for p in top:
        sub_cap_id = p["sub_cap_id"]
        sows = _evidence_sow(sub_cap_id)
        benchmarks = _evidence_benchmarks(sub_cap_id)
        news = _evidence_news(sub_cap_id)
        sources_count += len(sows) + len(benchmarks) + len(news)
        sources_blob = (
            "\n".join(
                f"- SOW {s['sow_id']} ({s['client']}, {s['status']}): {s['excerpt']}"
                for s in sows
            )
            + "\n"
            + "\n".join(
                f"- BENCH {b['metric_id']} {b['cohort_id']} {b['period']} verdict={b['verdict']}"
                f" p50={b.get('p50')}"
                for b in benchmarks
            )
            + "\n"
            + "\n".join(
                f"- NEWS [{n['source']}] {n['title']}" for n in news
            )
        )
        narrative, recommendation, chain_id, cost = _produce_narrative(p, sources_blob)
        total_cost += cost
        delta = _delta_vs_previous(sub_cap_id, subvertical=subvertical, previous_period=previous)
        priorities.append(
            PriorityNarrative(
                sub_cap_id=sub_cap_id,
                sub_cap_name=p.get("sub_cap_name", ""),
                state=p.get("state"),
                score=p.get("score"),
                confidence=p.get("confidence"),
                narrative=narrative,
                recommendation=recommendation,
                evidence_sows=sows,
                evidence_benchmarks=benchmarks,
                evidence_news=news,
                delta=delta,
                chain_id=chain_id,
                cost_usd=cost,
            )
        )

    summary = _executive_summary(subvertical, period, priorities)
    digest_id = _digest_id(subvertical, period)

    digest = StrategicDigest(
        digest_id=digest_id,
        subvertical=subvertical,
        period=period,
        previous_period=previous,
        generated_at=started.isoformat(),
        model="opus",
        priorities=[asdict(p) for p in priorities],
        summary=summary,
        sources_count=sources_count,
        total_cost_usd=total_cost,
    )

    if persist:
        repo.upsert(DIGEST_COLLECTION, digest_id, asdict(digest))
        run_id = f"digest-run-{int(started.timestamp())}"
        repo.upsert(
            DIGEST_RUNS_COLLECTION,
            run_id,
            {
                "id": run_id,
                "digest_id": digest_id,
                "subvertical": subvertical,
                "period": period,
                "started_at": started.isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "priorities_emitted": len(priorities),
                "total_cost_usd": total_cost,
            },
        )
    return digest


def _executive_summary(subvertical: str, period: str, priorities: list[PriorityNarrative]) -> str:
    if not priorities:
        return (
            f"No actionable priorities identified for {subvertical} in {period}; "
            "the lifecycle engine reports zero RISING/STABLE/EMERGING subcaps in this segment."
        )
    rising = [p for p in priorities if p.state == "RISING"]
    head = priorities[0]
    return (
        f"{period} priorities for {subvertical}: {len(priorities)} subcaps shortlisted, "
        f"{len(rising)} in RISING. Lead is {head.sub_cap_name} ({head.sub_cap_id}) at "
        f"score {head.score:.0f}. Evidence pulled from internal SOWs, peer benchmarks, "
        f"and recent news / trends. Each priority below ships with a recommendation."
    )


def list_digests(subvertical: str | None = None, limit: int = 50) -> list[dict]:
    items = list(get_repository().list(DIGEST_COLLECTION))
    if subvertical:
        items = [d for d in items if d.get("subvertical") == subvertical]
    items.sort(key=lambda d: (d.get("period", ""), d.get("subvertical", "")), reverse=True)
    return items[:limit]


def get_digest(digest_id: str) -> dict | None:
    return get_repository().get(DIGEST_COLLECTION, digest_id)
