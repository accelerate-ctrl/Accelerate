"""Vendor Intelligence — adoption per cohort, news events, win/loss heatmap.

Per spec §9 / ARCHITECTURE Batch 6.

Sources (all already ingested in earlier batches):

    Batch 5 technographics  — vendor stack per company (BuiltWith / Wappalyzer)
    Batch 5 cohort engine   — company → cohort assignments
    Batch 4 news + trends   — vendor mentions in published news / analyst trends

Outputs (deterministic, no LLM):

    vendors          — per-vendor summary: companies, cohorts, news mentions,
                       category, ai_assist_signal (if applicable)
    adoption matrix  — vendor × cohort → adoption % with company list
    news feed        — recent vendor-tagged news, newest first

Live-mode swap-ins gate on Settings.use_gcp + per-vendor key envs.  All
data here flows from the Repository abstraction so the public API is
identical between dev + prod.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from .repository import get_repository

logger = logging.getLogger(__name__)

VENDORS_COLLECTION = "vendor_profiles"
ADOPTION_COLLECTION = "vendor_adoption"
EVENTS_COLLECTION = "vendor_events"
RUN_COLLECTION = "vendor_intel_runs"


@dataclass
class VendorProfile:
    vendor_id: str
    name: str
    category: str | None
    companies: list[str]
    cohorts: list[str]
    news_mentions: int
    avg_confidence: float
    last_seen_at: str | None
    ai_signal_avg: float | None


@dataclass
class CohortAdoption:
    vendor_id: str
    cohort_id: str
    adopters: list[str]
    cohort_size: int
    adoption_pct: float
    avg_confidence: float


@dataclass
class RunSummary:
    run_id: str
    started_at: str
    completed_at: str
    vendors_loaded: int
    adoption_rows: int
    events_loaded: int


# ─── Helpers ────────────────────────────────────────────────────────────────


def _vendor_id(name: str) -> str:
    """Stable slug for vendor display name."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _cohort_companies() -> dict[str, list[str]]:
    """Return cohort_id → list of companies that fall in that cohort.

    Uses Batch 5 benchmark_observations (which already have cohort_ids
    pre-computed) to avoid re-running the cohort matcher here.
    """
    repo = get_repository()
    out: dict[str, set[str]] = {}
    for obs in repo.list("benchmark_observations"):
        company = obs.get("company")
        if not company or company == "(extrapolated)":
            continue
        for cid in obs.get("cohort_ids") or []:
            out.setdefault(cid, set()).add(company)
    return {k: sorted(v) for k, v in out.items()}


def _company_cohorts() -> dict[str, list[str]]:
    """Return company → list of cohorts.  Inverse of _cohort_companies()."""
    repo = get_repository()
    out: dict[str, set[str]] = {}
    for obs in repo.list("benchmark_observations"):
        company = obs.get("company")
        if not company or company == "(extrapolated)":
            continue
        for cid in obs.get("cohort_ids") or []:
            out.setdefault(company, set()).add(cid)
    return {k: sorted(v) for k, v in out.items()}


def _cohort_sizes() -> dict[str, int]:
    return {c: len(companies) for c, companies in _cohort_companies().items()}


def _technographic_rows() -> list[dict]:
    """Read raw technographic seed via the same loader benchmarks used.

    We re-load the seed JSONs because the benchmarks_service stores only
    the AI-assist signal as an observation; the full vendor list is in
    the source files.
    """
    from ..config import get_settings
    from .benchmarks_service import DEFAULT_TECHNOGRAPHICS_DIR, _load_json_dir, _resolve_dir

    s = get_settings()
    tdir = _resolve_dir(s.local_technographics_dir, DEFAULT_TECHNOGRAPHICS_DIR)
    if not tdir:
        return []
    return _load_json_dir(tdir)


def _news_mentions_for(vendor_name: str) -> tuple[int, str | None]:
    """Count news + trends rows that mention the vendor; return latest published_at."""
    repo = get_repository()
    needle = vendor_name.lower()
    count = 0
    latest: datetime | None = None
    for collection in ("news_items", "trends_items"):
        for item in repo.list(collection):
            blob = (item.get("title") or "") + " " + (item.get("text") or "")
            if needle in blob.lower():
                count += 1
                ts = item.get("published_at")
                try:
                    dt = datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
                    if latest is None or dt > latest:
                        latest = dt
                except Exception:
                    continue
    return count, latest.isoformat() if latest else None


# ─── Compute + persist ──────────────────────────────────────────────────────


def refresh() -> RunSummary:
    repo = get_repository()
    started = datetime.now(timezone.utc)
    with repo.defer_persist():
        return _refresh_inner(started=started)


def _refresh_inner(*, started) -> RunSummary:
    repo = get_repository()

    # 1) Build per-vendor aggregates from technographic rows
    rows = _technographic_rows()
    company_to_cohorts = _company_cohorts()
    cohort_sizes = _cohort_sizes()

    vendor_acc: dict[str, dict] = {}
    cohort_acc: dict[tuple[str, str], dict] = {}

    for row in rows:
        company = row.get("company")
        ai_signal = row.get("ai_assist_signal")
        for v in row.get("vendors") or []:
            vname = v.get("vendor", "?")
            vid = _vendor_id(vname)
            entry = vendor_acc.setdefault(
                vid,
                {
                    "vendor_id": vid,
                    "name": vname,
                    "category": v.get("category"),
                    "companies": set(),
                    "cohorts": set(),
                    "confidences": [],
                    "ai_signals": [],
                },
            )
            entry["companies"].add(company)
            entry["confidences"].append(float(v.get("confidence") or 0))
            if ai_signal is not None:
                entry["ai_signals"].append(float(ai_signal))
            for cid in company_to_cohorts.get(company, []):
                entry["cohorts"].add(cid)
                key = (vid, cid)
                acc = cohort_acc.setdefault(
                    key,
                    {
                        "vendor_id": vid,
                        "vendor_name": vname,
                        "cohort_id": cid,
                        "adopters": set(),
                        "confidences": [],
                    },
                )
                acc["adopters"].add(company)
                acc["confidences"].append(float(v.get("confidence") or 0))

    # 2) Persist vendor profiles
    for vid, e in vendor_acc.items():
        news_count, last_news = _news_mentions_for(e["name"])
        avg_conf = sum(e["confidences"]) / len(e["confidences"]) if e["confidences"] else 0.0
        ai_avg = sum(e["ai_signals"]) / len(e["ai_signals"]) if e["ai_signals"] else None
        profile = VendorProfile(
            vendor_id=vid,
            name=e["name"],
            category=e["category"],
            companies=sorted(e["companies"]),
            cohorts=sorted(e["cohorts"]),
            news_mentions=news_count,
            avg_confidence=round(avg_conf, 3),
            last_seen_at=last_news,
            ai_signal_avg=round(ai_avg, 2) if ai_avg is not None else None,
        )
        repo.upsert(VENDORS_COLLECTION, vid, asdict(profile))

    # 3) Persist cohort adoption rows
    adoption_rows = 0
    for (vid, cid), acc in cohort_acc.items():
        cohort_size = cohort_sizes.get(cid, 0)
        adopters = sorted(acc["adopters"])
        confs = acc["confidences"]
        rec = CohortAdoption(
            vendor_id=vid,
            cohort_id=cid,
            adopters=adopters,
            cohort_size=cohort_size,
            adoption_pct=(len(adopters) / cohort_size * 100.0) if cohort_size else 0.0,
            avg_confidence=round(sum(confs) / len(confs), 3) if confs else 0.0,
        )
        rid = f"adop-{vid}-{cid}"
        repo.upsert(ADOPTION_COLLECTION, rid, {**asdict(rec), "id": rid})
        adoption_rows += 1

    # 4) News events feed (vendor mentions, sorted by publication time)
    events_count = 0
    for vid, e in vendor_acc.items():
        needle = e["name"].lower()
        for collection in ("news_items", "trends_items"):
            for item in repo.list(collection):
                blob = (item.get("title") or "") + " " + (item.get("text") or "")
                if needle not in blob.lower():
                    continue
                eid = f"evt-{vid}-{item.get('id','?')}"
                repo.upsert(
                    EVENTS_COLLECTION,
                    eid,
                    {
                        "id": eid,
                        "vendor_id": vid,
                        "vendor_name": e["name"],
                        "kind": item.get("kind", collection.replace("_items", "")),
                        "title": item.get("title"),
                        "text": item.get("text"),
                        "url": item.get("url"),
                        "source": item.get("source"),
                        "published_at": item.get("published_at"),
                        "indexed_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                events_count += 1

    completed = datetime.now(timezone.utc)
    run_id = f"vendor-intel-{int(started.timestamp())}"
    summary = RunSummary(
        run_id=run_id,
        started_at=started.isoformat(),
        completed_at=completed.isoformat(),
        vendors_loaded=len(vendor_acc),
        adoption_rows=adoption_rows,
        events_loaded=events_count,
    )
    repo.upsert(RUN_COLLECTION, run_id, asdict(summary))
    return summary


# ─── Reads ──────────────────────────────────────────────────────────────────


def list_vendors(category: str | None = None, limit: int = 200) -> list[dict]:
    items = list(get_repository().list(VENDORS_COLLECTION))
    if category:
        items = [v for v in items if v.get("category") == category]
    items.sort(key=lambda v: (-len(v.get("companies") or []), v.get("name") or ""))
    return items[:limit]


def get_vendor(vendor_id: str) -> dict | None:
    return get_repository().get(VENDORS_COLLECTION, vendor_id)


def list_adoption(
    vendor_id: str | None = None, cohort_id: str | None = None, limit: int = 500,
) -> list[dict]:
    items = list(get_repository().list(ADOPTION_COLLECTION))
    if vendor_id:
        items = [a for a in items if a.get("vendor_id") == vendor_id]
    if cohort_id:
        items = [a for a in items if a.get("cohort_id") == cohort_id]
    items.sort(key=lambda a: (-float(a.get("adoption_pct") or 0), a.get("vendor_id", "")))
    return items[:limit]


def heatmap() -> dict:
    """Return {vendors: [...], cohorts: [...], cells: [{vendor_id, cohort_id, pct}]}."""
    rows = list_adoption(limit=10000)
    vendors = sorted({r["vendor_id"] for r in rows})
    cohorts = sorted({r["cohort_id"] for r in rows})
    cells = [
        {
            "vendor_id": r["vendor_id"],
            "cohort_id": r["cohort_id"],
            "adoption_pct": round(r["adoption_pct"], 1),
            "adopters": r["adopters"],
            "cohort_size": r["cohort_size"],
        }
        for r in rows
    ]
    return {"vendors": vendors, "cohorts": cohorts, "cells": cells}


def list_events(vendor_id: str | None = None, limit: int = 200) -> list[dict]:
    items = list(get_repository().list(EVENTS_COLLECTION))
    if vendor_id:
        items = [e for e in items if e.get("vendor_id") == vendor_id]
    items.sort(key=lambda e: e.get("published_at", ""), reverse=True)
    return items[:limit]


# ─── Phase 2.3 — evidence-driven vendor × subcap heatmap ───────────────────
#
# Per TRD §11 / Schema §5.5: the operator-facing vendor heatmap must be
# derived from real signals (vendor_events joined to news_items.impact
# .affected_subcaps), not the fixture-based vendor×cohort technographic
# join. The legacy adoption heatmap is kept; this new function returns
# a (vendor × subcap) matrix scored by the highest magnitude seen.


_MAG_SCORE = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


def _news_item_by_event_id(eid: str, news_index: dict[str, dict]) -> dict | None:
    """Resolve the source news_item for a vendor_event.

    Vendor events are stored with id pattern ``evt-{vendor_id}-{news_id}``;
    extracting the news_id is enough to look up the underlying news item
    in O(1) when we have an index built from a single repo.list().
    """
    if not eid or not eid.startswith("evt-"):
        return None
    # Vendor id can contain dashes (e.g. ``salesforce-data-cloud``);
    # find the last segment that matches a known news_id by trial.
    # We try each ``-`` split; first hit wins.
    remainder = eid[4:]  # strip ``evt-``
    parts = remainder.split("-")
    for i in range(1, len(parts)):
        candidate = "-".join(parts[i:])
        if candidate in news_index:
            return news_index[candidate]
    return None


def subcap_evidence_heatmap() -> dict:
    """Return a vendor × subcap matrix derived from vendor_events
    joined to news_items.impact.affected_subcaps.

    Each cell carries the highest magnitude seen across all matching
    events plus the event count and the most recent published_at, so
    the UI can render both severity colour and recency.

    Returns ``{vendors: [...], subcaps: [...], cells: [{vendor_id,
    sub_cap_id, magnitude, event_count, latest_event}]}``.
    """
    repo = get_repository()
    events = repo.list(EVENTS_COLLECTION)
    news = repo.list("news_items")
    news_index = {n["id"]: n for n in news if n.get("id")}

    # (vendor_id, sub_cap_id) → {magnitude_score, event_count, latest_event,
    #                            vendor_name}
    cells: dict[tuple[str, str], dict] = {}
    for evt in events:
        vid = evt.get("vendor_id")
        if not vid:
            continue
        item = _news_item_by_event_id(evt.get("id", ""), news_index)
        # Fallback: also try the legacy direct ``news_id`` field if the
        # event recorded one explicitly.
        if item is None:
            direct = evt.get("news_id")
            if direct and direct in news_index:
                item = news_index[direct]
        if item is None:
            continue
        impact = item.get("impact") or {}
        affected = impact.get("affected_subcaps") or []
        # Legacy flat list — synthesise LOW magnitude entries when the
        # structured payload isn't there yet (Phase 2.1 back-compat).
        if not affected and impact.get("affects_subcaps"):
            affected = [
                {"sub_cap_id": s, "magnitude": "LOW", "rationale": ""}
                for s in impact["affects_subcaps"]
            ]
        for entry in affected:
            sid = entry.get("sub_cap_id")
            mag = (entry.get("magnitude") or "LOW").upper()
            if not sid:
                continue
            score = _MAG_SCORE.get(mag, 1)
            key = (vid, sid)
            cell = cells.setdefault(key, {
                "vendor_id": vid,
                "sub_cap_id": sid,
                "vendor_name": evt.get("vendor_name"),
                "magnitude_score": 0,
                "event_count": 0,
                "latest_event": None,
            })
            cell["event_count"] += 1
            if score > cell["magnitude_score"]:
                cell["magnitude_score"] = score
            published = evt.get("published_at") or evt.get("indexed_at")
            if published and (cell["latest_event"] is None or published > cell["latest_event"]):
                cell["latest_event"] = published

    score_to_mag = {3: "HIGH", 2: "MEDIUM", 1: "LOW"}
    out_cells = []
    for cell in cells.values():
        out_cells.append({
            "vendor_id": cell["vendor_id"],
            "sub_cap_id": cell["sub_cap_id"],
            "vendor_name": cell.get("vendor_name"),
            "magnitude": score_to_mag.get(cell["magnitude_score"], "LOW"),
            "event_count": cell["event_count"],
            "latest_event": cell["latest_event"],
        })

    vendors = sorted({c["vendor_id"] for c in out_cells})
    subcaps = sorted({c["sub_cap_id"] for c in out_cells})
    return {
        "vendors": vendors,
        "subcaps": subcaps,
        "cells": out_cells,
        "total_events_joined": sum(c["event_count"] for c in out_cells),
    }


def latest_run() -> dict | None:
    runs = list(get_repository().list(RUN_COLLECTION))
    if not runs:
        return None
    runs.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return runs[0]
