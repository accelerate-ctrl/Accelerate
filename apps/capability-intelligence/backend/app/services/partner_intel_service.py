"""Partner Intelligence — release-notes scan + L2 capability mapping.

Pipeline:

  1. Load partner registry from `config/partners.yml`.
  2. For each partner, fetch the most recent release-notes entries
     (RSS when available, else local seed file fallback). Capped at
     `lookback_days` for cost control.
  3. For each entry, ask Gemini Flash to extract the feature(s) it
     announces, with a strict JSON schema:
         [{feature, summary, category, impact_class}, ...]
  4. Embed each feature blurb (256-d hash embedding) and match it
     against every L1_Capability in the catalogue via cosine
     similarity. Top-1 with score ≥ THRESHOLD_MATCH (0.55) is the
     mapped L1.
  5. Persist two artefacts:
       * `partner_releases` collection — the raw release entry +
         extracted features + mapped L1s + adversary score.
       * `suggestions` collection — one `partner_feature_add` row per
         feature whose mapping confidence is HIGH but the catalogue
         doesn't list that feature on the mapped L1 yet (gap).

Output is consumed by:
  * `vendor_intel_service.releases(partner=)` for the timeline view
  * `vendor_intel_service.catalogue_gaps()` for the suggestions feed
  * `QA & Audit Dashboard` for the cross-source signal aggregator
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .repository import get_repository

log = logging.getLogger(__name__)

RELEASES_COLLECTION = "partner_releases"
SUGGESTIONS_COLLECTION = "suggestions"
RUNS_COLLECTION = "partner_release_runs"

THRESHOLD_MATCH = 0.55         # cosine — below this we don't claim a mapping
THRESHOLD_GAP = 0.70           # high-confidence mapping → "catalogue gap" suggestion
MAX_ENTRIES_PER_PARTNER = 25   # cap per scan to bound LLM cost


# ─── Registry ───────────────────────────────────────────────────────────────


@dataclass
class Partner:
    code: str
    name: str
    category: str
    release_notes: str
    rss_url: str | None
    lookback_days: int = 90
    user_agent: str = "Zennify-CapabilityIntelligence/1.0"


def load_partners() -> list[Partner]:
    """Resolve config/partners.yml by searching up from cwd."""
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / "config" / "partners.yml"
        if candidate.exists():
            data = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
            return [Partner(**p) for p in (data.get("partners") or [])]
    log.warning("config/partners.yml not found from cwd=%s", cwd)
    return []


# ─── Source fetching ────────────────────────────────────────────────────────


@dataclass
class RawEntry:
    title: str
    summary: str
    url: str | None
    published_at: str
    partner_code: str
    source: str  # "rss" | "seed"


def _seed_dir() -> Path | None:
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / "test-data" / "partners"
        if candidate.exists():
            return candidate
    return None


def _fetch_rss(partner: Partner) -> list[RawEntry]:  # pragma: no cover — live cloud only
    if not partner.rss_url:
        return []
    try:
        import feedparser  # type: ignore[import-not-found]
    except ImportError:
        return []
    parsed = feedparser.parse(partner.rss_url)
    out: list[RawEntry] = []
    for e in parsed.entries[:MAX_ENTRIES_PER_PARTNER]:
        published = (
            e.get("published") or e.get("updated") or datetime.now(timezone.utc).isoformat()
        )
        out.append(RawEntry(
            title=(e.get("title") or "")[:200],
            summary=(e.get("summary") or e.get("description") or "")[:1200],
            url=e.get("link"),
            published_at=published,
            partner_code=partner.code,
            source="rss",
        ))
    return out


def _fetch_seed(partner: Partner) -> list[RawEntry]:
    base = _seed_dir()
    if not base:
        return []
    candidate = base / f"{partner.code}.json"
    if not candidate.exists():
        return []
    try:
        data = json.loads(candidate.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("could not parse %s: %s", candidate, exc)
        return []
    if not isinstance(data, list):
        return []
    out: list[RawEntry] = []
    for raw in data[:MAX_ENTRIES_PER_PARTNER]:
        out.append(RawEntry(
            title=(raw.get("title") or "")[:200],
            summary=(raw.get("summary") or raw.get("description") or "")[:1200],
            url=raw.get("url") or raw.get("link"),
            published_at=raw.get("published_at") or datetime.now(timezone.utc).isoformat(),
            partner_code=partner.code,
            source="seed",
        ))
    return out


def _fetch_entries(partner: Partner, *, live_mode: bool) -> list[RawEntry]:
    """Live mode prefers RSS; falls back to seed if RSS is empty/missing."""
    if live_mode:
        entries = _fetch_rss(partner)
        if entries:
            return entries
    return _fetch_seed(partner)


# ─── Feature extraction (Gemini Flash, JSON schema) ────────────────────────


_EXTRACT_SYSTEM = (
    "You are a Zennify analyst reading a partner release-notes entry. "
    "Identify every product feature it announces and classify each one. "
    "Output STRICT JSON only — no prose."
)

_EXTRACT_PROMPT = """\
Partner: {partner_name}
Entry title: {title}
Published: {published_at}
URL: {url}
Body:
---
{body}
---

Return JSON: a top-level array (may be empty if the entry isn't a
feature release):

[
  {{
    "feature": "<short name, ≤8 words>",
    "summary": "<one sentence, ≤30 words, what changed>",
    "impact_class": "new_feature | enhancement | deprecation | bug_fix",
    "category_hint": "<one of: integration, analytics, automation, ux, security, ai, data, workflow>"
  }},
  ...
]

Rules:
* Be conservative — bug fixes and admin/internal updates are still
  included but flagged correctly.
* If the entry is purely marketing, return [].
"""


def _ensure_list(obj: object) -> list:
    """Parse possibly-text-wrapped JSON into a list."""
    import re as _re
    if isinstance(obj, list):
        return obj
    if isinstance(obj, str):
        m = _re.search(r"\[.*\]", obj, _re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(0))
                return parsed if isinstance(parsed, list) else []
            except Exception:  # noqa: BLE001
                pass
    return []


def extract_features(entry: RawEntry, partner: Partner) -> list[dict]:
    """LLM call. Returns 0–N feature dicts, with safe defaults on failure."""
    from .llm.router import LlmRequest, ModelKind
    from .llm.router import call as llm_call

    prompt = _EXTRACT_PROMPT.format(
        partner_name=partner.name,
        title=entry.title,
        published_at=entry.published_at,
        url=entry.url or "?",
        body=entry.summary,
    )
    try:
        resp = llm_call(LlmRequest(
            model=ModelKind.GEMINI_FLASH,
            prompt=prompt,
            system=_EXTRACT_SYSTEM,
            max_tokens=512,
            metadata={
                "operation_type": "partner_release_extract",
                "partner_code": partner.code,
            },
        ))
        raw = _ensure_list(resp.text)
    except Exception as exc:  # noqa: BLE001
        log.warning("feature extract failed for %s/%s: %s",
                    partner.code, entry.title[:40], exc)
        raw = []

    out: list[dict] = []
    for item in raw[:8]:
        if not isinstance(item, dict):
            continue
        feature = (item.get("feature") or "").strip()
        if not feature:
            continue
        impact = item.get("impact_class") or "new_feature"
        if impact not in ("new_feature", "enhancement", "deprecation", "bug_fix"):
            impact = "new_feature"
        out.append({
            "feature": feature[:120],
            "summary": (item.get("summary") or "")[:280],
            "impact_class": impact,
            "category_hint": (item.get("category_hint") or "")[:40],
        })
    return out


# ─── L1/L2 matching (semantic) ──────────────────────────────────────────────


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _build_l1_index() -> list[tuple[dict, list[float]]]:
    """Embed every L1_Capability + its child subcap summaries so feature
    matching has the broadest possible context to match against."""
    from .llm.embeddings import embed_text

    repo = get_repository()
    l1_rows = list(repo.list("l1_capabilities"))
    subcaps_by_l1: dict[str, list[dict]] = {}
    for sc in repo.list("subcaps"):
        l1 = sc.get("l1_capability") or sc.get("l1_capability_id")
        if l1:
            subcaps_by_l1.setdefault(l1, []).append(sc)

    out: list[tuple[dict, list[float]]] = []
    for l1 in l1_rows:
        l1_name = l1.get("l1_capability") or l1.get("name") or ""
        text = " ".join(filter(None, [
            l1_name,
            l1.get("description"),
            l1.get("category_id"),
            " ".join((sc.get("sub_cap_name") or "") for sc in subcaps_by_l1.get(l1_name, [])[:8]),
        ]))
        if not text.strip():
            continue
        out.append((l1, embed_text(text)))
    return out


def match_to_l1(feature_text: str, index: list[tuple[dict, list[float]]]) -> dict | None:
    """Return the best-matching L1 record + score, or None if below threshold."""
    if not index:
        return None
    from .llm.embeddings import embed_text
    vec = embed_text(feature_text)
    best: tuple[float, dict] | None = None
    for l1, l1_vec in index:
        score = _cosine(vec, l1_vec)
        if best is None or score > best[0]:
            best = (score, l1)
    if best is None or best[0] < THRESHOLD_MATCH:
        return None
    return {"score": round(best[0], 4), "l1": best[1]}


# ─── Catalogue gap detection ────────────────────────────────────────────────


def _l1_already_covers(feature: str, l1_name: str, repo) -> bool:
    """Heuristic: does any subcap under this L1 mention a token from the
    feature name? Bounds the "is this a real gap?" check without firing
    another LLM call."""
    tokens = {t.lower() for t in feature.replace("/", " ").replace("-", " ").split() if len(t) > 3}
    if not tokens:
        return True  # too generic to be a gap
    for sc in repo.list("subcaps"):
        if sc.get("l1_capability") != l1_name:
            continue
        blob = " ".join([
            sc.get("sub_cap_name") or "",
            sc.get("description") or "",
            " ".join((f.get("feature_name") or "") for f in (sc.get("l4_features") or [])),
        ]).lower()
        if any(tok in blob for tok in tokens):
            return True
    return False


# ─── Orchestration ──────────────────────────────────────────────────────────


@dataclass
class ScanResult:
    run_id: str
    started_at: str
    completed_at: str
    entries_seen: int
    features_extracted: int
    releases_persisted: int
    suggestions_created: int
    per_partner: dict[str, dict] = field(default_factory=dict)


def _release_id(partner_code: str, entry: RawEntry) -> str:
    seed = f"{partner_code}::{entry.url or entry.title}::{entry.published_at}"
    return "rel-" + hashlib.sha256(seed.encode()).hexdigest()[:12]


def run_scan(*, limit_per_partner: int = MAX_ENTRIES_PER_PARTNER) -> dict:
    """Full pipeline. Idempotent — same entry produces the same release_id
    so re-runs just upsert. Returns a per-partner summary."""
    from ..config import get_settings
    s = get_settings()
    partners = load_partners()
    if not partners:
        return {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "error": "partners.yml not found",
            "partners": [],
        }

    repo = get_repository()
    started = datetime.now(timezone.utc)
    index = _build_l1_index()

    entries_seen = 0
    features_total = 0
    releases_persisted = 0
    suggestions_created = 0
    per_partner: dict[str, dict] = {}

    for partner in partners:
        entries = _fetch_entries(partner, live_mode=s.llm_live_mode)[:limit_per_partner]
        p_features = 0
        p_releases = 0
        p_suggestions = 0
        for entry in entries:
            entries_seen += 1
            features = extract_features(entry, partner)
            p_features += len(features)
            features_total += len(features)

            # Map each feature → L1.
            mapped: list[dict] = []
            for f in features:
                match = match_to_l1(f"{f['feature']} — {f['summary']}", index)
                if not match:
                    mapped.append({**f, "mapped_l1": None, "score": 0.0, "is_gap": False})
                    continue
                l1_name = (match["l1"].get("l1_capability") or match["l1"].get("name"))
                is_gap = (
                    match["score"] >= THRESHOLD_GAP
                    and not _l1_already_covers(f["feature"], l1_name, repo)
                )
                mapped.append({
                    **f,
                    "mapped_l1": l1_name,
                    "mapped_l1_id": match["l1"].get("id") or l1_name,
                    "score": match["score"],
                    "is_gap": is_gap,
                })

            rid = _release_id(partner.code, entry)
            record = {
                "id": rid,
                "release_id": rid,
                "partner_code": partner.code,
                "partner_name": partner.name,
                "category": partner.category,
                "title": entry.title,
                "summary": entry.summary,
                "url": entry.url,
                "published_at": entry.published_at,
                "source": entry.source,
                "features": mapped,
                "scanned_at": started.isoformat(),
            }
            repo.upsert(RELEASES_COLLECTION, rid, record)
            p_releases += 1
            releases_persisted += 1

            # Emit suggestion rows for high-confidence gaps.
            for f in mapped:
                if not f.get("is_gap"):
                    continue
                sid = "sug-" + hashlib.sha256(f"{rid}::{f['feature']}".encode()).hexdigest()[:10]
                existing = repo.get(SUGGESTIONS_COLLECTION, sid)
                if existing and existing.get("status") in ("applied", "rejected"):
                    continue  # don't re-open already-decided suggestions
                repo.upsert(SUGGESTIONS_COLLECTION, sid, {
                    "id": sid,
                    "kind": "partner_feature_add",
                    "origin": "partner",
                    "target": f.get("mapped_l1"),
                    "title": f"Add `{f['feature']}` to {f.get('mapped_l1') or 'L1'}",
                    "rationale": (
                        f"{partner.name} shipped {f['feature']} "
                        f"({f['impact_class']}). {f['summary']} "
                        f"Match confidence {f['score']:.2f}. "
                        f"Source: {entry.url or '(no url)'}."
                    ),
                    "status": "pending",
                    "chain_id": None,
                    "gate_overall": "n/a",
                    "created_at": started.isoformat(),
                    "created_by": "partner_release_scan",
                    "source_refs": {
                        "release_id": rid,
                        "partner_code": partner.code,
                        "feature": f,
                    },
                })
                p_suggestions += 1
                suggestions_created += 1

        per_partner[partner.code] = {
            "name": partner.name,
            "entries": len(entries),
            "features": p_features,
            "releases": p_releases,
            "gap_suggestions": p_suggestions,
            "source": "rss" if (s.llm_live_mode and partner.rss_url) else "seed",
        }

    completed = datetime.now(timezone.utc)
    run_id = f"partner-scan-{int(started.timestamp())}"
    summary = ScanResult(
        run_id=run_id,
        started_at=started.isoformat(),
        completed_at=completed.isoformat(),
        entries_seen=entries_seen,
        features_extracted=features_total,
        releases_persisted=releases_persisted,
        suggestions_created=suggestions_created,
        per_partner=per_partner,
    ).__dict__
    repo.upsert(RUNS_COLLECTION, run_id, summary)
    return summary


# ─── Read-side ──────────────────────────────────────────────────────────────


def list_releases(*, partner_code: str | None = None,
                  days: int | None = None,
                  limit: int = 200) -> list[dict]:
    rows = list(get_repository().list(RELEASES_COLLECTION))
    if partner_code:
        rows = [r for r in rows if r.get("partner_code") == partner_code]
    if days is not None:
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        rows = [r for r in rows if (r.get("published_at") or "") >= cutoff]
    rows.sort(key=lambda r: r.get("published_at", ""), reverse=True)
    return rows[:limit]


def catalogue_gaps() -> list[dict]:
    """Aggregate the high-confidence partner-feature gaps grouped by
    target L1 + partner, sorted by recency."""
    by_l1: dict[str, dict[str, Any]] = {}
    for rel in list_releases(limit=500):
        for f in (rel.get("features") or []):
            if not f.get("is_gap"):
                continue
            l1 = f.get("mapped_l1") or "Unknown L1"
            bucket = by_l1.setdefault(l1, {
                "l1_capability": l1,
                "features": [],
                "partners": set(),
                "last_seen": "",
            })
            bucket["features"].append({
                **f,
                "partner_code": rel.get("partner_code"),
                "partner_name": rel.get("partner_name"),
                "release_id": rel.get("release_id"),
                "release_url": rel.get("url"),
                "published_at": rel.get("published_at"),
                "release_title": rel.get("title"),
            })
            bucket["partners"].add(rel.get("partner_code") or "?")
            if (rel.get("published_at") or "") > bucket["last_seen"]:
                bucket["last_seen"] = rel.get("published_at") or ""

    out = []
    for bucket in by_l1.values():
        bucket["partners"] = sorted(bucket["partners"])
        bucket["count"] = len(bucket["features"])
        out.append(bucket)
    out.sort(key=lambda b: (b.get("last_seen") or "", b["count"]), reverse=True)
    return out


def latest_run() -> dict | None:
    runs = list(get_repository().list(RUNS_COLLECTION))
    if not runs:
        return None
    runs.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return runs[0]
