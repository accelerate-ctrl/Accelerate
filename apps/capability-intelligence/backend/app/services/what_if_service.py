"""What-If Simulator — pure-function ripple analysis.

Per spec §13 / ARCHITECTURE Batch 8.

Apply a list of hypothetical actions to the synthesis layer (Batch 6
lifecycle scores + Batch 6 vendor adoption + Batch 6 client journeys)
WITHOUT mutating the repository. Returns a diff summarising what would
change, so users can experiment safely.

Supported actions
-----------------

    add_sow_mention       {sub_cap_id, client, status?}
        Bumps the subcap's lifecycle score by adding one synthetic
        active SOW mention; recomputes only that subcap's state.

    set_lifecycle_state   {sub_cap_id, state}
        Forces a state transition; surfaces it as a hypothetical
        transition row (no rule-based recompute, just override).

    promote_vendor        {vendor_id, cohort_id, adoption_pct}
        Overrides the (vendor, cohort) adoption % and recomputes
        the heatmap delta.

    add_news_mention      {sub_cap_id}
        Adds one fresh-dated news mention; bumps news_last_90d.

The simulator is deliberately read-only: it builds a working copy of
the affected rows, applies the actions, and returns the diff. No
``repo.upsert`` calls happen here.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from .repository import get_repository

logger = logging.getLogger(__name__)


@dataclass
class Action:
    kind: str
    target: dict[str, Any] = field(default_factory=dict)


@dataclass
class StateChange:
    sub_cap_id: str
    sub_cap_name: str
    before: dict[str, Any]
    after: dict[str, Any]


@dataclass
class AdoptionChange:
    vendor_id: str
    cohort_id: str
    before_pct: float
    after_pct: float


@dataclass
class SimulationResult:
    actions_applied: int
    state_changes: list[dict]
    adoption_changes: list[dict]
    new_transitions: list[dict]
    summary: str
    computed_at: str


# ─── Action dispatch ────────────────────────────────────────────────────────


def _apply_add_sow_mention(
    target: dict,
    *,
    scores: dict,
    transitions: list,
) -> StateChange | None:
    sub_cap_id = target.get("sub_cap_id")
    if not sub_cap_id or sub_cap_id not in scores:
        return None
    before = deepcopy(scores[sub_cap_id])
    score = scores[sub_cap_id]
    sig = score.setdefault("signals", {}).copy()
    sig["sow_active"] = (sig.get("sow_active") or 0) + 1
    sig["sow_recency_days"] = 0
    score["signals"] = sig
    new_score = _recompute_score(sig)
    new_state = _classify(sig, new_score)
    if new_state != score.get("state") or abs(new_score - (score.get("score") or 0)) >= 0.5:
        score["score"] = new_score
        score["state"] = new_state
    return StateChange(
        sub_cap_id=sub_cap_id,
        sub_cap_name=score.get("sub_cap_name", ""),
        before={"state": before.get("state"), "score": before.get("score")},
        after={"state": score["state"], "score": score["score"]},
    )


def _apply_set_lifecycle_state(target: dict, *, scores: dict) -> StateChange | None:
    sub_cap_id = target.get("sub_cap_id")
    new_state = (target.get("state") or "").upper()
    if not sub_cap_id or sub_cap_id not in scores:
        return None
    valid_states = {"EMERGING", "RISING", "STABLE", "DECLINING", "FADING", "DEAD"}
    if new_state not in valid_states:
        return None
    before = deepcopy(scores[sub_cap_id])
    scores[sub_cap_id]["state"] = new_state
    return StateChange(
        sub_cap_id=sub_cap_id,
        sub_cap_name=scores[sub_cap_id].get("sub_cap_name", ""),
        before={"state": before.get("state"), "score": before.get("score")},
        after={"state": new_state, "score": before.get("score")},
    )


def _apply_promote_vendor(target: dict, *, adoption: dict) -> AdoptionChange | None:
    vendor_id = target.get("vendor_id")
    cohort_id = target.get("cohort_id")
    new_pct = float(target.get("adoption_pct", 0))
    if not vendor_id or not cohort_id:
        return None
    key = f"adop-{vendor_id}-{cohort_id}"
    before = adoption.get(key, {"adoption_pct": 0.0})
    new_row = {**before, "vendor_id": vendor_id, "cohort_id": cohort_id, "adoption_pct": new_pct}
    adoption[key] = new_row
    return AdoptionChange(
        vendor_id=vendor_id,
        cohort_id=cohort_id,
        before_pct=float(before.get("adoption_pct") or 0.0),
        after_pct=new_pct,
    )


def _apply_add_news_mention(target: dict, *, scores: dict) -> StateChange | None:
    sub_cap_id = target.get("sub_cap_id")
    if not sub_cap_id or sub_cap_id not in scores:
        return None
    before = deepcopy(scores[sub_cap_id])
    score = scores[sub_cap_id]
    sig = score.setdefault("signals", {}).copy()
    sig["news_last_90d"] = (sig.get("news_last_90d") or 0) + 1
    sig["news_recency_days"] = 0
    score["signals"] = sig
    new_score = _recompute_score(sig)
    new_state = _classify(sig, new_score)
    score["score"] = new_score
    score["state"] = new_state
    return StateChange(
        sub_cap_id=sub_cap_id,
        sub_cap_name=score.get("sub_cap_name", ""),
        before={"state": before.get("state"), "score": before.get("score")},
        after={"state": new_state, "score": new_score},
    )


# Mirrors lifecycle_service._score / _classify_state but operates on dict signals.
def _recompute_score(sig: dict) -> float:
    sow_component = min(100.0, (sig.get("sow_active", 0)) * 25 + (sig.get("sow_prospect", 0)) * 15)
    story_component = min(
        100.0,
        (sig.get("canonical_stories", 0)) * 0.3 + (sig.get("jira_stories", 0)) * 5,
    )
    news_component = min(
        100.0,
        (sig.get("news_last_90d", 0)) * 25 + (sig.get("trends_last_90d", 0)) * 15,
    )
    benchmark_component = min(
        100.0,
        (sig.get("benchmark_full", 0)) * 35
        + (sig.get("benchmark_indicative", 0)) * 18
        + (sig.get("benchmark_exploratory", 0)) * 6,
    )
    return round(
        0.40 * sow_component
        + 0.20 * story_component
        + 0.20 * news_component
        + 0.20 * benchmark_component,
        2,
    )


def _classify(sig: dict, score: float) -> str:
    has_active = (
        (sig.get("sow_active") or 0) > 0
        or (sig.get("news_last_90d") or 0) > 0
        or (sig.get("jira_stories") or 0) > 0
    )
    has_any = has_active or any(
        sig.get(k, 0)
        for k in (
            "canonical_stories",
            "sow_prospect",
            "benchmark_full",
            "benchmark_indicative",
            "benchmark_exploratory",
            "trends_last_90d",
            "ai_extrapolations",
        )
    )
    sow_age = sig.get("sow_recency_days")
    news_age = sig.get("news_recency_days")
    if not has_any and score == 0.0:
        return "DEAD"
    if not has_active:
        if (sig.get("canonical_stories") or 0) > 0 or (
            (sig.get("benchmark_full") or 0) + (sig.get("benchmark_indicative") or 0)
        ) > 0:
            return "FADING" if score < 25 else "DECLINING"
        return "FADING"
    if score >= 70 and (sow_age is None or sow_age <= 30):
        return "RISING" if (news_age is not None and news_age <= 60) else "STABLE"
    if score >= 45:
        return "RISING" if ((sig.get("sow_prospect") or 0) > 0 or (sig.get("news_last_90d") or 0) >= 2) else "STABLE"
    if score >= 20:
        return "EMERGING"
    return "EMERGING"


# ─── Public ─────────────────────────────────────────────────────────────────


def simulate(actions: list[dict]) -> SimulationResult:
    repo = get_repository()
    scores = {s["sub_cap_id"]: deepcopy(s) for s in repo.list("lifecycle_scores")}
    adoption = {
        f"adop-{a['vendor_id']}-{a['cohort_id']}": deepcopy(a)
        for a in repo.list("vendor_adoption")
    }

    state_changes: list[StateChange] = []
    adoption_changes: list[AdoptionChange] = []
    new_transitions: list[dict] = []
    applied = 0

    for raw in actions:
        kind = (raw.get("kind") or "").strip()
        target = raw.get("target") or {}
        change: StateChange | AdoptionChange | None = None
        if kind == "add_sow_mention":
            change = _apply_add_sow_mention(
                target, scores=scores, transitions=new_transitions,
            )
        elif kind == "set_lifecycle_state":
            change = _apply_set_lifecycle_state(target, scores=scores)
        elif kind == "promote_vendor":
            change = _apply_promote_vendor(target, adoption=adoption)
        elif kind == "add_news_mention":
            change = _apply_add_news_mention(target, scores=scores)
        else:
            logger.info("ignoring unknown what-if kind: %s", kind)
            continue
        if change is None:
            continue
        applied += 1
        if isinstance(change, StateChange):
            if change.before["state"] != change.after["state"]:
                new_transitions.append({
                    "sub_cap_id": change.sub_cap_id,
                    "from_state": change.before["state"],
                    "to_state": change.after["state"],
                    "score": change.after["score"],
                    "transitioned_at": datetime.now(timezone.utc).isoformat(),
                })
            state_changes.append(asdict(change))
        else:
            adoption_changes.append(asdict(change))

    summary = (
        f"Applied {applied}/{len(actions)} actions → "
        f"{len(state_changes)} lifecycle deltas, "
        f"{len(adoption_changes)} adoption deltas, "
        f"{len(new_transitions)} new transitions."
    )

    return SimulationResult(
        actions_applied=applied,
        state_changes=state_changes,
        adoption_changes=adoption_changes,
        new_transitions=new_transitions,
        summary=summary,
        computed_at=datetime.now(timezone.utc).isoformat(),
    )
