"""Lifecycle engine — 6-state weighted scoring per subcap.

Per spec §8 / ARCHITECTURE Batch 6.

States (in order of maturity → decline):

    EMERGING    — first appears in evidence; no SOWs yet, low news cadence
    RISING      — recent + accelerating signals (SOW mentions ↑, news ↑)
    STABLE      — broad mature adoption; healthy cohort distribution
    DECLINING   — signal cadence slowing; SOWs aging out
    FADING      — only stale SOWs / sunset projects; no new evidence
    DEAD        — no live signals at all; subcap candidate for retirement

Scoring inputs (deterministic, no LLM):

    1. SOW evidence       (Batch 3) — recency-weighted active+prospect mentions
    2. Story velocity     (Batch 3) — canonical + Jira count, recent
    3. News + trends      (Batch 4) — last 90d cadence
    4. Benchmark coverage (Batch 5) — verdict mix across cohorts
    5. AI-extrapolated    (Batch 5) — chain volume implies attention

The weighted score (0..100) combines those signals; states are bucketed by
score + age-of-most-recent-signal.

State transitions are append-only in :data:`TRANSITIONS_COLLECTION` so we
have a history to drive Lifecycle Manager kanban + Subcap Deep Dive.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .repository import get_repository

logger = logging.getLogger(__name__)

SCORES_COLLECTION = "lifecycle_scores"
TRANSITIONS_COLLECTION = "lifecycle_transitions"
RUN_COLLECTION = "lifecycle_runs"

STATE_EMERGING = "EMERGING"
STATE_RISING = "RISING"
STATE_STABLE = "STABLE"
STATE_DECLINING = "DECLINING"
STATE_FADING = "FADING"
STATE_DEAD = "DEAD"

ALL_STATES = (
    STATE_EMERGING,
    STATE_RISING,
    STATE_STABLE,
    STATE_DECLINING,
    STATE_FADING,
    STATE_DEAD,
)


@dataclass
class Signals:
    sow_active: int = 0
    sow_prospect: int = 0
    sow_inactive: int = 0
    sow_archived: int = 0
    sow_recency_days: int | None = None  # days since most-recent SOW ingest
    canonical_stories: int = 0
    jira_stories: int = 0
    news_last_90d: int = 0
    news_recency_days: int | None = None
    trends_last_90d: int = 0
    benchmark_indicative: int = 0
    benchmark_full: int = 0  # BENCHMARK verdict count
    benchmark_exploratory: int = 0
    ai_extrapolations: int = 0


@dataclass
class LifecycleScore:
    sub_cap_id: str
    sub_cap_name: str
    state: str
    score: float
    confidence: float  # 0..1 rough; 1.0 = many signals, 0.0 = none
    signals: dict[str, Any]
    last_signal_at: str | None
    computed_at: str


@dataclass
class RunSummary:
    run_id: str
    started_at: str
    completed_at: str
    subcaps_scored: int
    state_distribution: dict[str, int]
    transitions: int
    inputs_seen: dict[str, int]


# ─── Helpers ────────────────────────────────────────────────────────────────


def _parse_iso(ts: str | None) -> datetime | None:
    """Parse ISO 8601 to a *UTC-aware* datetime, regardless of input.

    Older Batch-3 services stored timestamps via :func:`datetime.utcnow`
    which is naive; we coerce those to aware-UTC so downstream subtraction
    against ``datetime.now(timezone.utc)`` doesn't raise.
    """
    if not ts:
        return None
    try:
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _age_days(ts: str | None, *, ref: datetime | None = None) -> int | None:
    parsed = _parse_iso(ts)
    if not parsed:
        return None
    ref = ref or datetime.now(timezone.utc)
    return max(0, (ref - parsed).days)


@dataclass
class _IndexedRepo:
    """Pre-grouped views over the source collections; built once per run."""
    sows_by_id: dict
    mentions_by_subcap: dict
    canonical_by_subcap: dict
    jira_by_subcap: dict
    news_by_subcap: dict   # subcap_id → list of (parsed_dt, item)
    trends_by_subcap: dict
    distributions_by_metric: dict  # metric_id → list[dict]
    extrapolations_by_metric: dict  # metric_id → count


def _build_index() -> _IndexedRepo:
    repo = get_repository()
    sows_by_id = {s.get("sow_id"): s for s in repo.list("sows")}
    mentions_by_subcap: dict = {}
    for m in repo.list("sow_mentions"):
        mentions_by_subcap.setdefault(m.get("sub_cap_id"), []).append(m)
    canonical_by_subcap: dict = {}
    for s in repo.list("stories_canonical"):
        canonical_by_subcap.setdefault(s.get("sub_cap_id"), []).append(s)
    jira_by_subcap: dict = {}
    for s in repo.list("jira_stories"):
        jira_by_subcap.setdefault(s.get("sub_cap_id"), []).append(s)
    news_by_subcap: dict = {}
    for n in repo.list("news_items"):
        parsed = _parse_iso(n.get("published_at"))
        for sid in n.get("sub_cap_hits") or []:
            news_by_subcap.setdefault(sid, []).append((parsed, n))
    trends_by_subcap: dict = {}
    for t in repo.list("trends_items"):
        parsed = _parse_iso(t.get("published_at"))
        for sid in t.get("sub_cap_hits") or []:
            trends_by_subcap.setdefault(sid, []).append((parsed, t))
    distributions_by_metric: dict = {}
    for d in repo.list("benchmark_distributions"):
        distributions_by_metric.setdefault(d.get("metric_id"), []).append(d)
    extrapolations_by_metric: dict = {}
    for o in repo.list("benchmark_observations"):
        if o.get("is_extrapolated"):
            extrapolations_by_metric[o.get("metric_id")] = (
                extrapolations_by_metric.get(o.get("metric_id"), 0) + 1
            )
    return _IndexedRepo(
        sows_by_id=sows_by_id,
        mentions_by_subcap=mentions_by_subcap,
        canonical_by_subcap=canonical_by_subcap,
        jira_by_subcap=jira_by_subcap,
        news_by_subcap=news_by_subcap,
        trends_by_subcap=trends_by_subcap,
        distributions_by_metric=distributions_by_metric,
        extrapolations_by_metric=extrapolations_by_metric,
    )


def _gather_signals(
    sub_cap_id: str,
    *,
    now: datetime,
    idx: _IndexedRepo,
    metric_subcap_index: dict[str, set[str]],
) -> Signals:
    sig = Signals()

    # SOW mentions (Batch 3)
    most_recent_sow: datetime | None = None
    for m in idx.mentions_by_subcap.get(sub_cap_id, []):
        sow = idx.sows_by_id.get(m.get("sow_id"), {})
        status = (sow.get("status") or "").lower()
        if status == "active":
            sig.sow_active += 1
        elif status == "prospect":
            sig.sow_prospect += 1
        elif status == "inactive":
            sig.sow_inactive += 1
        else:
            sig.sow_archived += 1
        ingested = _parse_iso(sow.get("ingested_at") or m.get("ingested_at"))
        if ingested and (most_recent_sow is None or ingested > most_recent_sow):
            most_recent_sow = ingested
    if most_recent_sow:
        sig.sow_recency_days = max(0, (now - most_recent_sow).days)

    sig.canonical_stories = len(idx.canonical_by_subcap.get(sub_cap_id, []))
    sig.jira_stories = len(idx.jira_by_subcap.get(sub_cap_id, []))

    # News + trends (Batch 4)
    cutoff_90 = now - timedelta(days=90)
    most_recent_news: datetime | None = None
    for parsed, _ in idx.news_by_subcap.get(sub_cap_id, []):
        if parsed and parsed >= cutoff_90:
            sig.news_last_90d += 1
        if parsed and (most_recent_news is None or parsed > most_recent_news):
            most_recent_news = parsed
    for parsed, _ in idx.trends_by_subcap.get(sub_cap_id, []):
        if parsed and parsed >= cutoff_90:
            sig.trends_last_90d += 1
    if most_recent_news:
        sig.news_recency_days = max(0, (now - most_recent_news).days)

    # Benchmark coverage — bridge via metric→subcap index
    matching_metrics = {m for m, sids in metric_subcap_index.items() if sub_cap_id in sids}
    for metric_id in matching_metrics:
        for d in idx.distributions_by_metric.get(metric_id, []):
            v = d.get("verdict")
            if v == "BENCHMARK":
                sig.benchmark_full += 1
            elif v == "INDICATIVE":
                sig.benchmark_indicative += 1
            elif v == "EXPLORATORY":
                sig.benchmark_exploratory += 1
        sig.ai_extrapolations += idx.extrapolations_by_metric.get(metric_id, 0)

    return sig


def _build_metric_subcap_index(all_subcap_ids: list[str]) -> dict[str, set[str]]:
    """For every metric, pre-compute the set of subcap_ids it maps to.

    Avoids re-evaluating wildcard patterns inside the per-subcap loop.
    """
    out: dict[str, set[str]] = {}
    for metric_id, patterns in _load_metric_mappings().items():
        sids = {sid for sid in all_subcap_ids if any(_pattern_match(p, sid) for p in patterns)}
        out[metric_id] = sids
    return out


def _pattern_match(pattern: str, sub_cap_id: str) -> bool:
    if pattern.endswith("*"):
        return sub_cap_id.startswith(pattern[:-1])
    return pattern == sub_cap_id


# Cache the loaded metrics → subcap_mappings to avoid YAML re-parse hot loop.
_METRIC_MAPPINGS_CACHE: dict[str, list[str]] | None = None


def _load_metric_mappings() -> dict[str, list[str]]:
    global _METRIC_MAPPINGS_CACHE
    if _METRIC_MAPPINGS_CACHE is not None:
        return _METRIC_MAPPINGS_CACHE
    from .benchmarks_service import _load_metrics  # late import (cycle-safe)
    _METRIC_MAPPINGS_CACHE = {
        m["metric_id"]: m.get("subcap_mappings") or [] for m in _load_metrics()
    }
    return _METRIC_MAPPINGS_CACHE


# NOTE: _subcap_in_metric was removed in favour of the pre-built
# metric_subcap_index. _pattern_match below replaces the inline glob check.


# ─── Scoring ────────────────────────────────────────────────────────────────


def _score(sig: Signals) -> tuple[float, float]:
    """Return (score, confidence) — both in 0..100."""

    # Component scores 0..100 with explicit weights:
    #  - active SOWs are the strongest signal of ongoing demand
    #  - story velocity confirms active engineering attention
    #  - recent news shows market pull
    #  - benchmark coverage shows the metric has measurable peer adoption

    sow_component = min(100.0, sig.sow_active * 25 + sig.sow_prospect * 15)
    story_component = min(100.0, sig.canonical_stories * 0.3 + sig.jira_stories * 5)
    news_component = min(100.0, sig.news_last_90d * 25 + sig.trends_last_90d * 15)
    benchmark_component = min(
        100.0,
        sig.benchmark_full * 35 + sig.benchmark_indicative * 18 + sig.benchmark_exploratory * 6,
    )

    weighted = (
        0.40 * sow_component
        + 0.20 * story_component
        + 0.20 * news_component
        + 0.20 * benchmark_component
    )

    # Confidence: how many signal categories are non-zero?
    seen = sum(
        bool(c)
        for c in (sow_component, story_component, news_component, benchmark_component)
    )
    confidence = seen / 4.0
    return round(weighted, 2), round(confidence, 2)


def _classify_state(sig: Signals, score: float) -> str:
    has_active_signal = (
        sig.sow_active > 0
        or sig.news_last_90d > 0
        or sig.jira_stories > 0
    )
    has_any_signal = has_active_signal or any(
        c
        for c in (
            sig.canonical_stories,
            sig.sow_prospect,
            sig.benchmark_full,
            sig.benchmark_indicative,
            sig.benchmark_exploratory,
            sig.trends_last_90d,
            sig.ai_extrapolations,
        )
    )
    sow_age = sig.sow_recency_days
    news_age = sig.news_recency_days

    # No signals at all → DEAD
    if not has_any_signal and score == 0.0:
        return STATE_DEAD

    # Stale-only signals → FADING / DECLINING
    if not has_active_signal:
        if sig.canonical_stories > 0 or sig.benchmark_indicative + sig.benchmark_full > 0:
            # has historical evidence but nothing recent
            return STATE_FADING if score < 25 else STATE_DECLINING
        return STATE_FADING

    # Active signals — bucket by score + recency
    if score >= 70 and (sow_age is None or sow_age <= 30):
        return STATE_RISING if (news_age is not None and news_age <= 60) else STATE_STABLE
    if score >= 45:
        return STATE_RISING if (sig.sow_prospect > 0 or sig.news_last_90d >= 2) else STATE_STABLE
    if score >= 20:
        return STATE_EMERGING
    return STATE_EMERGING


def _last_signal_at(sig: Signals, *, now: datetime) -> str | None:
    candidates: list[datetime] = []
    if sig.sow_recency_days is not None:
        candidates.append(now - timedelta(days=sig.sow_recency_days))
    if sig.news_recency_days is not None:
        candidates.append(now - timedelta(days=sig.news_recency_days))
    if not candidates:
        return None
    return max(candidates).isoformat()


# ─── Public API ─────────────────────────────────────────────────────────────


def recompute_all() -> RunSummary:
    repo = get_repository()
    started = datetime.now(timezone.utc)
    with repo.defer_persist():
        return _recompute_inner(started=started)


def _recompute_inner(*, started) -> RunSummary:
    repo = get_repository()
    subcaps = list(repo.list("subcaps"))
    inputs_seen = {
        "subcaps": len(subcaps),
        "sow_mentions": len(repo.list("sow_mentions")),
        "stories_canonical": len(repo.list("stories_canonical")),
        "jira_stories": len(repo.list("jira_stories")),
        "news_items": len(repo.list("news_items")),
        "trends_items": len(repo.list("trends_items")),
        "benchmark_distributions": len(repo.list("benchmark_distributions")),
    }

    # Reset metric-mapping cache so we pick up newly-loaded metrics.
    global _METRIC_MAPPINGS_CACHE
    _METRIC_MAPPINGS_CACHE = None

    state_dist: dict[str, int] = {s: 0 for s in ALL_STATES}
    transitions = 0
    now = datetime.now(timezone.utc)

    # Build the indexed views of every input collection ONCE — without this
    # the inner loop scans 4844-row stories collection 199 times.
    idx = _build_index()
    metric_subcap_index = _build_metric_subcap_index(
        [sc["sub_cap_id"] for sc in subcaps if sc.get("sub_cap_id")]
    )

    for sc in subcaps:
        sub_cap_id = sc.get("sub_cap_id")
        if not sub_cap_id:
            continue
        sig = _gather_signals(
            sub_cap_id, now=now, idx=idx, metric_subcap_index=metric_subcap_index,
        )
        score, confidence = _score(sig)
        state = _classify_state(sig, score)
        state_dist[state] = state_dist.get(state, 0) + 1

        previous = repo.get(SCORES_COLLECTION, sub_cap_id)
        record = LifecycleScore(
            sub_cap_id=sub_cap_id,
            sub_cap_name=sc.get("sub_cap_name", ""),
            state=state,
            score=score,
            confidence=confidence,
            signals=asdict(sig),
            last_signal_at=_last_signal_at(sig, now=now),
            computed_at=now.isoformat(),
        )
        repo.upsert(SCORES_COLLECTION, sub_cap_id, asdict(record))

        prev_state = (previous or {}).get("state")
        if prev_state and prev_state != state:
            tid = f"trans-{sub_cap_id}-{int(now.timestamp())}"
            repo.upsert(
                TRANSITIONS_COLLECTION,
                tid,
                {
                    "id": tid,
                    "sub_cap_id": sub_cap_id,
                    "from_state": prev_state,
                    "to_state": state,
                    "score": score,
                    "transitioned_at": now.isoformat(),
                },
            )
            transitions += 1

    completed = datetime.now(timezone.utc)
    run_id = f"lifecycle-{int(started.timestamp())}"
    summary = RunSummary(
        run_id=run_id,
        started_at=started.isoformat(),
        completed_at=completed.isoformat(),
        subcaps_scored=len(subcaps),
        state_distribution=state_dist,
        transitions=transitions,
        inputs_seen=inputs_seen,
    )
    repo.upsert(RUN_COLLECTION, run_id, asdict(summary))
    return summary


def list_scores(state: str | None = None, limit: int = 500) -> list[dict]:
    items = list(get_repository().list(SCORES_COLLECTION))
    if state:
        items = [i for i in items if i.get("state") == state]
    items.sort(key=lambda i: (-float(i.get("score") or 0), i.get("sub_cap_id", "")))
    return items[:limit]


def get_score(sub_cap_id: str) -> dict | None:
    return get_repository().get(SCORES_COLLECTION, sub_cap_id)


def list_transitions(sub_cap_id: str | None = None, limit: int = 200) -> list[dict]:
    items = list(get_repository().list(TRANSITIONS_COLLECTION))
    if sub_cap_id:
        items = [i for i in items if i.get("sub_cap_id") == sub_cap_id]
    items.sort(key=lambda i: i.get("transitioned_at", ""), reverse=True)
    return items[:limit]


def state_distribution() -> dict[str, int]:
    out: dict[str, int] = {s: 0 for s in ALL_STATES}
    for s in get_repository().list(SCORES_COLLECTION):
        st = s.get("state")
        if st:
            out[st] = out.get(st, 0) + 1
    return out


def latest_run() -> dict | None:
    runs = list(get_repository().list(RUN_COLLECTION))
    if not runs:
        return None
    runs.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return runs[0]
