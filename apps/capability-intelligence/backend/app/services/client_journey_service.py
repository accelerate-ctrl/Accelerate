"""Client Journey Atlas + DMA App handoff packet.

Per spec §10 / ARCHITECTURE Batch 6.

Synthesizes a client view from:

    Batch 3 SOWs              — active / prospect / inactive engagements
    Batch 3 mentions          — which subcaps each SOW touched
    Batch 3 stories           — canonical + Jira velocity
    Batch 5 technographics    — vendor stack per company
    Batch 6 lifecycle scores  — state of every subcap the client touches
    Batch 6 vendor_intel      — peer adoption % for the client's vendors

Two-tier API:

    GET  /api/clients/{name}/journey      → page-friendly JSON
    GET  /api/clients/{name}/dma-packet   → flat JSON for downstream DMA app
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from .repository import get_repository

logger = logging.getLogger(__name__)

JOURNEYS_COLLECTION = "client_journeys"


@dataclass
class TouchedSubcap:
    sub_cap_id: str
    sub_cap_name: str
    state: str | None
    score: float | None
    confidence: float | None
    sow_count: int
    sow_excerpts: list[str]
    canonical_story_count: int
    jira_story_count: int


@dataclass
class VendorStackEntry:
    vendor: str
    category: str | None
    confidence: float
    cohort_adoption: list[dict]  # [{cohort_id, adoption_pct}]


@dataclass
class ClientJourney:
    client_name: str
    sow_count_active: int
    sow_count_prospect: int
    sow_count_inactive: int
    sow_count_archived: int
    cohorts: list[str]
    subverticals: list[str]
    asset_size_usd_bn: float | None
    touched_subcaps: list[dict]  # serialized TouchedSubcap
    vendor_stack: list[dict]
    state_distribution: dict[str, int]
    most_recent_signal_at: str | None
    computed_at: str


# ─── Build journey ──────────────────────────────────────────────────────────


def _build_journey(client_name: str) -> ClientJourney | None:
    repo = get_repository()
    needle = client_name.strip().lower()

    # 1) SOWs that match the client (case-insensitive on canonical client_name)
    matching_sows = [
        s for s in repo.list("sows")
        if (s.get("client_name") or "").strip().lower() == needle
    ]
    if not matching_sows:
        return None

    sow_ids = {s["sow_id"] for s in matching_sows}
    counts = {"active": 0, "prospect": 0, "inactive": 0, "archived": 0}
    for s in matching_sows:
        counts[(s.get("status") or "archived").lower()] = counts.get(
            (s.get("status") or "archived").lower(), 0
        ) + 1

    # 2) Mentions tied to those SOWs
    mentions = [m for m in repo.list("sow_mentions") if m.get("sow_id") in sow_ids]
    by_subcap: dict[str, list[dict]] = {}
    for m in mentions:
        by_subcap.setdefault(m["sub_cap_id"], []).append(m)

    # 3) Subcap detail + lifecycle state for each touched subcap
    subcaps_by_id = {sc["sub_cap_id"]: sc for sc in repo.list("subcaps")}
    lifecycle_by_id = {sc["sub_cap_id"]: sc for sc in repo.list("lifecycle_scores")}
    canon_by_subcap: dict[str, int] = {}
    for st in repo.list("stories_canonical"):
        sid = st.get("sub_cap_id")
        if sid:
            canon_by_subcap[sid] = canon_by_subcap.get(sid, 0) + 1
    jira_by_subcap: dict[str, int] = {}
    for st in repo.list("jira_stories"):
        sid = st.get("sub_cap_id")
        if sid:
            jira_by_subcap[sid] = jira_by_subcap.get(sid, 0) + 1

    touched: list[TouchedSubcap] = []
    state_dist: dict[str, int] = {}
    for sid, ms in by_subcap.items():
        sc = subcaps_by_id.get(sid, {})
        lc = lifecycle_by_id.get(sid, {})
        excerpts = [m.get("excerpt", "") for m in ms[:3] if m.get("excerpt")]
        touched.append(
            TouchedSubcap(
                sub_cap_id=sid,
                sub_cap_name=sc.get("sub_cap_name", ""),
                state=lc.get("state"),
                score=lc.get("score"),
                confidence=lc.get("confidence"),
                sow_count=len({m["sow_id"] for m in ms}),
                sow_excerpts=excerpts,
                canonical_story_count=canon_by_subcap.get(sid, 0),
                jira_story_count=jira_by_subcap.get(sid, 0),
            ),
        )
        if (st := lc.get("state")):
            state_dist[st] = state_dist.get(st, 0) + 1
    touched.sort(key=lambda t: -t.sow_count)

    # 4) Cohorts + subverticals + assets from technographic / benchmark observations
    bench_obs = [
        o for o in repo.list("benchmark_observations")
        if (o.get("company") or "").strip().lower() == needle
    ]
    cohorts = sorted({c for o in bench_obs for c in (o.get("cohort_ids") or [])})
    subverticals = sorted({o.get("subvertical") for o in bench_obs if o.get("subvertical")})
    asset_size = next(
        (o.get("asset_size_usd_bn") for o in bench_obs if o.get("asset_size_usd_bn")),
        None,
    )

    # 5) Vendor stack — search the technographic seed via vendor adoption rows
    vendor_stack: list[VendorStackEntry] = []
    adoption_index: dict[str, list[dict]] = {}
    for adop in repo.list("vendor_adoption"):
        adoption_index.setdefault(adop["vendor_id"], []).append(
            {"cohort_id": adop["cohort_id"], "adoption_pct": round(adop["adoption_pct"], 1)},
        )
    # Read the raw technographic JSON to pull this client's vendor stack
    from .vendor_intel_service import _technographic_rows, _vendor_id

    for row in _technographic_rows():
        if (row.get("company") or "").strip().lower() != needle:
            continue
        for v in row.get("vendors") or []:
            vid = _vendor_id(v.get("vendor", ""))
            vendor_stack.append(
                VendorStackEntry(
                    vendor=v.get("vendor", "?"),
                    category=v.get("category"),
                    confidence=float(v.get("confidence") or 0),
                    cohort_adoption=adoption_index.get(vid, []),
                ),
            )

    # 6) Most-recent signal
    candidates: list[str] = []
    for s in matching_sows:
        if ts := s.get("ingested_at"):
            candidates.append(ts)
    most_recent = max(candidates) if candidates else None

    journey = ClientJourney(
        client_name=matching_sows[0].get("client_name") or client_name,
        sow_count_active=counts.get("active", 0),
        sow_count_prospect=counts.get("prospect", 0),
        sow_count_inactive=counts.get("inactive", 0),
        sow_count_archived=counts.get("archived", 0),
        cohorts=cohorts,
        subverticals=subverticals,
        asset_size_usd_bn=asset_size,
        touched_subcaps=[asdict(t) for t in touched],
        vendor_stack=[asdict(v) for v in vendor_stack],
        state_distribution=state_dist,
        most_recent_signal_at=most_recent,
        computed_at=datetime.now(timezone.utc).isoformat(),
    )
    return journey


# ─── Public API ─────────────────────────────────────────────────────────────


def get_journey(client_name: str, *, persist: bool = True) -> dict | None:
    journey = _build_journey(client_name)
    if not journey:
        return None
    if persist:
        get_repository().upsert(JOURNEYS_COLLECTION, _key(journey.client_name), asdict(journey))
    return asdict(journey)


def list_journeys(limit: int = 100) -> list[dict]:
    items = list(get_repository().list(JOURNEYS_COLLECTION))
    items.sort(key=lambda j: j.get("computed_at", ""), reverse=True)
    return items[:limit]


def refresh_all() -> dict[str, Any]:
    """Build a journey for every distinct client in the SOWs collection."""
    repo = get_repository()
    seen: dict[str, dict] = {}
    with repo.defer_persist():
        for s in repo.list("sows"):
            client = s.get("client_name") or "?"
            if client in seen:
                continue
            journey = get_journey(client, persist=True)
            if journey:
                seen[client] = journey
    return {
        "clients_built": len(seen),
        "client_names": sorted(seen.keys()),
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def dma_packet(client_name: str) -> dict | None:
    """Flatten a journey into a DMA-friendly handoff packet."""
    journey = _build_journey(client_name)
    if not journey:
        return None
    j = asdict(journey)
    # DMA packet drops UI-only fields and adds a flat "priorities" list
    priorities = [
        {
            "sub_cap_id": t["sub_cap_id"],
            "sub_cap_name": t["sub_cap_name"],
            "state": t["state"],
            "score": t["score"],
            "sow_count": t["sow_count"],
        }
        for t in j["touched_subcaps"]
        if (t.get("state") or "").upper() in ("RISING", "STABLE", "EMERGING")
    ][:10]
    return {
        "schema_version": "dma-handoff-v1",
        "generated_at": j["computed_at"],
        "client": j["client_name"],
        "asset_size_usd_bn": j["asset_size_usd_bn"],
        "subverticals": j["subverticals"],
        "cohorts": j["cohorts"],
        "engagement": {
            "active": j["sow_count_active"],
            "prospect": j["sow_count_prospect"],
            "inactive": j["sow_count_inactive"],
            "archived": j["sow_count_archived"],
        },
        "vendor_stack": [
            {"vendor": v["vendor"], "category": v["category"], "confidence": v["confidence"]}
            for v in j["vendor_stack"]
        ],
        "state_distribution": j["state_distribution"],
        "priorities": priorities,
    }


def _key(name: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
