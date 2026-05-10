"""Persona-overlaid views.

Per spec §15 / ARCHITECTURE Batch 8.

Personas are stored on each subcap (Batch 1) as a list of strings
(e.g., ["CIO", "CDO", "Strategy & Planning Lead"]).  This service
indexes them, exposes them as first-class entities, and joins them
against Batch 6 lifecycle scores so a CIO / Architect / Compliance
Officer can see *their* slice of the catalogue.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

from .repository import get_repository

logger = logging.getLogger(__name__)


@dataclass
class Persona:
    name: str
    subcap_count: int
    rising_count: int
    stable_count: int
    fading_count: int
    pillars: list[str]
    sample_subcaps: list[dict]


def list_personas(limit: int = 200) -> list[dict]:
    """Distinct personas with rollup stats."""
    repo = get_repository()
    subcaps = list(repo.list("subcaps"))
    lifecycle = {s["sub_cap_id"]: s for s in repo.list("lifecycle_scores")}

    by_persona: dict[str, list[dict]] = {}
    for sc in subcaps:
        for p in sc.get("personas") or []:
            if p:
                by_persona.setdefault(p, []).append(sc)

    results: list[Persona] = []
    for name, sc_list in by_persona.items():
        states: Counter[str] = Counter()
        pillars: Counter[str] = Counter()
        for sc in sc_list:
            sid = sc.get("sub_cap_id")
            if not sid:
                continue
            ls = lifecycle.get(sid, {})
            states[ls.get("state", "?")] += 1
            if sc.get("pillar_id"):
                pillars[sc["pillar_id"]] += 1
        sorted_sc = sorted(
            sc_list,
            key=lambda x: -float(lifecycle.get(x.get("sub_cap_id", ""), {}).get("score") or 0),
        )
        results.append(
            Persona(
                name=name,
                subcap_count=len(sc_list),
                rising_count=states.get("RISING", 0),
                stable_count=states.get("STABLE", 0),
                fading_count=states.get("FADING", 0) + states.get("DEAD", 0),
                pillars=sorted(pillars.keys()),
                sample_subcaps=[
                    {
                        "sub_cap_id": sc.get("sub_cap_id"),
                        "sub_cap_name": sc.get("sub_cap_name"),
                        "pillar_id": sc.get("pillar_id"),
                        "state": lifecycle.get(sc.get("sub_cap_id", ""), {}).get("state"),
                        "score": lifecycle.get(sc.get("sub_cap_id", ""), {}).get("score"),
                    }
                    for sc in sorted_sc[:5]
                ],
            )
        )
    results.sort(key=lambda r: -r.subcap_count)
    return [asdict(r) for r in results[:limit]]


def get_persona_view(name: str, *, limit: int = 50) -> dict | None:
    """All subcaps for a persona, joined with lifecycle + Batch-3 SOW touches."""
    repo = get_repository()
    matches = [
        sc for sc in repo.list("subcaps")
        if name in (sc.get("personas") or [])
    ]
    if not matches:
        return None

    lifecycle = {s["sub_cap_id"]: s for s in repo.list("lifecycle_scores")}
    sow_touch_count: dict[str, int] = {}
    for m in repo.list("sow_mentions"):
        sid = m.get("sub_cap_id")
        if sid:
            sow_touch_count[sid] = sow_touch_count.get(sid, 0) + 1

    rows = []
    for sc in matches:
        sid = sc.get("sub_cap_id")
        ls = lifecycle.get(sid, {})
        rows.append({
            "sub_cap_id": sid,
            "sub_cap_name": sc.get("sub_cap_name"),
            "pillar_id": sc.get("pillar_id"),
            "category_id": sc.get("category_id"),
            "tier": sc.get("tier"),
            "state": ls.get("state"),
            "score": ls.get("score"),
            "confidence": ls.get("confidence"),
            "sow_touch_count": sow_touch_count.get(sid, 0),
        })
    rows.sort(key=lambda r: (-(r.get("score") or 0), r.get("sub_cap_id", "")))

    state_dist: Counter[str] = Counter(r.get("state") for r in rows if r.get("state"))

    return {
        "persona": name,
        "subcap_count": len(rows),
        "state_distribution": dict(state_dist),
        "subcaps": rows[:limit],
    }
