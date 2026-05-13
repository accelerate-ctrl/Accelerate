"""News + trends ingest.

Dev mode: reads JSON seed files from ``test-data/news/`` and
``test-data/trends/`` (one record per file or list per file).  Live mode:
parses RSS feeds via feedparser when ``Settings.news_feeds`` is populated.

Each news record is normalized to:

    {
      "id": "news-<sha-of-url>",
      "url": str | None,
      "title": str,
      "text": str,         # body or summary
      "source": str,       # domain
      "published_at": iso8601,
      "ingested_at": iso8601,
      "kind": "news" | "trend",
      "subverticals": [str],
      "sub_cap_hits": [str],
    }

After normalization the records are written to the ``news_items`` /
``trends_items`` collection AND indexed into the LLM vector store so the
consultant loop's external retrieval step can find them.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..config import get_settings
from .llm.vector_store import VectorStore
from .repository import get_repository
from .sow_service import extract_mentions  # reuse subcap mention extractor

logger = logging.getLogger(__name__)

NEWS_COLLECTION = "news_items"
TRENDS_COLLECTION = "trends_items"
RUN_COLLECTION = "news_ingest_runs"
DEFAULT_NEWS_DIR = "test-data/news"
DEFAULT_TRENDS_DIR = "test-data/trends"


@dataclass
class IngestSummary:
    run_id: str
    started_at: str
    completed_at: str
    news_loaded: int
    trends_loaded: int
    sources: list[str]
    schema_issues: list[str]


def _resolve_dir(configured: str | None, default_rel: str) -> Path | None:
    if configured:
        p = Path(configured)
        return p if p.exists() else None
    # search up from cwd looking for test-data/<sub>
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / default_rel
        if candidate.exists():
            return candidate
    return None


def _read_seed(directory: Path) -> list[dict]:
    items: list[dict] = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not parse %s: %s", path, exc)
            continue
        if isinstance(data, list):
            items.extend(data)
        elif isinstance(data, dict):
            items.append(data)
    return items


def _parse_rss(feed_url: str) -> list[dict]:
    """Live mode: pull feedparser entries.  Imported lazily."""
    import feedparser  # type: ignore[import-not-found]

    parsed = feedparser.parse(feed_url)
    out: list[dict] = []
    for e in parsed.entries:
        out.append({
            "url": e.get("link"),
            "title": e.get("title"),
            "text": e.get("summary", ""),
            "source": parsed.feed.get("title", feed_url),
            "published_at": e.get("published") or datetime.now(timezone.utc).isoformat(),
            "kind": "news",
        })
    return out


def _normalize(item: dict, kind: str, *, subcaps: list[dict]) -> dict:
    url = item.get("url") or ""
    nid = item.get("id") or _stable_id(url or item.get("title", ""), kind)
    text = item.get("text") or item.get("summary") or ""
    blob = (item.get("title") or "") + "\n" + text
    hits = extract_mentions([blob], subcaps) if subcaps else []
    return {
        "id": nid,
        "url": url or None,
        "title": item.get("title", "(untitled)"),
        "text": text,
        "source": item.get("source") or _domain(url) or "seed",
        "published_at": item.get("published_at") or datetime.now(timezone.utc).isoformat(),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "subverticals": item.get("subverticals", []),
        "sub_cap_hits": sorted({m.sub_cap_id for m in hits}),
    }


def _stable_id(seed: str, kind: str) -> str:
    digest = hashlib.sha256(seed.encode()).hexdigest()[:12]
    return f"{kind}-{digest}"


def _domain(url: str) -> str:
    try:
        return url.split("/")[2] if url else ""
    except IndexError:
        return ""


def _load_subcaps() -> list[dict]:
    return [s for s in get_repository().list("subcaps") if s.get("sub_cap_id")]


def refresh() -> IngestSummary:
    s = get_settings()
    repo = get_repository()
    started = datetime.now(timezone.utc)
    with repo.defer_persist():
        return _refresh_inner(s=s, repo=repo, started=started)


def _refresh_inner(*, s, repo, started) -> IngestSummary:
    issues: list[str] = []
    sources: list[str] = []
    subcaps = _load_subcaps()

    news_items: list[dict] = []
    trends_items: list[dict] = []

    # 1) Local seed files (always loaded — they're cheap fixtures)
    nd = _resolve_dir(s.local_news_dir, DEFAULT_NEWS_DIR)
    td = _resolve_dir(s.local_trends_dir, DEFAULT_TRENDS_DIR)
    if nd:
        sources.append(f"local:{nd}")
        for raw in _read_seed(nd):
            news_items.append(_normalize(raw, "news", subcaps=subcaps))
    if td:
        sources.append(f"local:{td}")
        for raw in _read_seed(td):
            trends_items.append(_normalize(raw, "trend", subcaps=subcaps))

    # 2) Live RSS — only when configured
    if s.news_feeds and s.llm_live_mode:
        for feed in s.news_feeds:
            try:
                for raw in _parse_rss(feed):
                    news_items.append(_normalize(raw, "news", subcaps=subcaps))
                sources.append(f"rss:{feed}")
            except Exception as exc:  # noqa: BLE001
                issues.append(f"rss {feed}: {exc}")

    # 3) Persist + index
    for item in news_items:
        repo.upsert(NEWS_COLLECTION, item["id"], item)
    for item in trends_items:
        repo.upsert(TRENDS_COLLECTION, item["id"], item)

    vs = VectorStore()
    for item in news_items + trends_items:
        vs.upsert(
            item["id"],
            (item.get("title") or "") + "\n" + (item.get("text") or ""),
            metadata={
                "kind": item["kind"],
                "source": item["source"],
                "published_at": item["published_at"],
                "url": item.get("url"),
            },
        )

    completed = datetime.now(timezone.utc)
    run_id = f"news-ingest-{int(started.timestamp())}"
    summary = IngestSummary(
        run_id=run_id,
        started_at=started.isoformat(),
        completed_at=completed.isoformat(),
        news_loaded=len(news_items),
        trends_loaded=len(trends_items),
        sources=sources,
        schema_issues=issues,
    )
    repo.upsert(RUN_COLLECTION, run_id, summary.__dict__)
    return summary


def list_news(limit: int = 100, sub_cap_id: str | None = None) -> list[dict]:
    items = sorted(
        get_repository().list(NEWS_COLLECTION),
        key=lambda r: r.get("published_at", ""),
        reverse=True,
    )
    if sub_cap_id:
        items = [i for i in items if sub_cap_id in (i.get("sub_cap_hits") or [])]
    return items[:limit]


def list_trends(limit: int = 100) -> list[dict]:
    items = sorted(
        get_repository().list(TRENDS_COLLECTION),
        key=lambda r: r.get("published_at", ""),
        reverse=True,
    )
    return items[:limit]


def latest_run() -> dict | None:
    runs = get_repository().list(RUN_COLLECTION)
    if not runs:
        return None
    runs.sort(key=lambda r: r.get("started_at", ""), reverse=True)
    return runs[0]


# ─── Impact synthesis ───────────────────────────────────────────────────────
#
# For each news item we ask Gemini Flash (cheap, ~$0.0003 per item) to:
#   1. Summarise the article in one sentence (≤30 words).
#   2. Classify catalogue impact: catalogue_extension | reinforcement |
#      benchmark_source | no_impact.
#   3. List affected sub_cap_ids (must come from the catalogue inventory).
#   4. Optionally suggest a brand-new sub_cap_id when the item describes
#      a capability the catalogue doesn't cover.
#   5. Confidence 0–1.
#
# Output is persisted onto the news item itself at `impact = {...}`. The UI
# renders these as insight cards. The function is idempotent — items
# already carrying a non-null `impact` block are skipped unless `force=True`.

IMPACT_CLASSES = ("catalogue_extension", "reinforcement", "benchmark_source", "no_impact")

_IMPACT_SYSTEM = (
    "You are a Zennify strategist judging whether a news article changes the "
    "FS-industry capability catalogue. Be precise, conservative, and ground "
    "every claim in the article body. Output STRICT JSON only — no prose."
)

_IMPACT_PROMPT_TPL = """\
Catalogue inventory (truncated to the most relevant 60 sub_caps):
{subcaps_blob}

News item:
  title:        {title}
  source:       {source}
  published_at: {published_at}
  url:          {url}
  body:
  ---
  {body}
  ---

Return JSON with this exact schema:
{{
  "summary": "<one sentence, ≤30 words, what the article says>",
  "impact_class": "<catalogue_extension | reinforcement | benchmark_source | no_impact>",
  "affects_subcaps": ["P1C…", "P1C…"],  // 0–4 ids drawn from the inventory above
  "suggests_new_subcap": null | {{
      "name": "<short capability name>",
      "rationale": "<why this isn't already covered>",
      "candidate_l1": "<one of the L1 capabilities in the inventory>"
  }},
  "confidence": 0.0–1.0
}}

Rules:
* Never invent a sub_cap_id that isn't in the inventory.
* "catalogue_extension" requires `suggests_new_subcap` to be non-null.
* "no_impact" means the article is FS-news but doesn't touch capability scope.
* "benchmark_source" means the article reports a quantitative benchmark we
  could ingest (cite the metric in `summary`).
"""


def _subcap_inventory_blob(subcaps: list[dict], limit: int = 60) -> str:
    """Render a compact inventory the LLM can match against. We surface
    id, name, L1, and a one-line description — enough for the model to
    pick the right anchor."""
    out = []
    for s in subcaps[:limit]:
        sid = s.get("sub_cap_id")
        name = (s.get("sub_cap_name") or s.get("name") or "").strip()
        l1 = s.get("l1_capability") or s.get("category_id") or ""
        desc = (s.get("description") or "").strip()[:160]
        out.append(f"  {sid} · {l1} · {name}{(' — ' + desc) if desc else ''}")
    return "\n".join(out) if out else "  (catalogue empty)"


def _ensure_dict(obj: object) -> dict:
    """Defensive JSON unwrap — the LLM occasionally returns text-wrapped JSON."""
    import json
    import re
    if isinstance(obj, dict):
        return obj
    if isinstance(obj, str):
        # Strip ```json … ``` fences if any
        m = re.search(r"\{.*\}", obj, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:  # noqa: BLE001
                pass
    return {}


def synthesise_impact(item: dict, *, subcaps: list[dict] | None = None) -> dict:
    """Run the Gemini-Flash impact classifier on one news item.

    Returns the impact dict (always with all five fields, with safe defaults
    if the LLM call fails). Caller is responsible for persisting it back to
    the news item.
    """
    from .llm.router import LlmRequest, ModelKind
    from .llm.router import call as llm_call
    subcaps = subcaps if subcaps is not None else _load_subcaps()
    prompt = _IMPACT_PROMPT_TPL.format(
        subcaps_blob=_subcap_inventory_blob(subcaps),
        title=(item.get("title") or "")[:200],
        source=item.get("source") or item.get("source_domain") or "?",
        published_at=item.get("published_at") or "?",
        url=item.get("url") or "?",
        body=(item.get("text") or item.get("body") or item.get("summary") or "")[:2400],
    )
    try:
        resp = llm_call(LlmRequest(
            model=ModelKind.GEMINI_FLASH,
            prompt=prompt,
            system=_IMPACT_SYSTEM,
            max_tokens=512,
            metadata={"operation_type": "news_impact_synthesis"},
        ))
        payload = _ensure_dict(resp.text)
    except Exception as exc:  # noqa: BLE001 — surface, don't propagate
        logger.warning("impact synth failed for %s: %s", item.get("id"), exc)
        payload = {}
    # Coerce + validate.
    klass = payload.get("impact_class") or "no_impact"
    if klass not in IMPACT_CLASSES:
        klass = "no_impact"
    affects = [s for s in (payload.get("affects_subcaps") or []) if isinstance(s, str)][:4]
    suggested = payload.get("suggests_new_subcap")
    if klass != "catalogue_extension":
        suggested = None
    elif not isinstance(suggested, dict):
        suggested = None
    try:
        conf = float(payload.get("confidence") or 0.0)
        conf = max(0.0, min(1.0, conf))
    except (TypeError, ValueError):
        conf = 0.0
    return {
        "summary": (payload.get("summary") or "")[:400],
        "impact_class": klass,
        "affects_subcaps": affects,
        "suggests_new_subcap": suggested,
        "confidence": round(conf, 3),
        "synthesised_at": datetime.now(timezone.utc).isoformat(),
    }


def synthesise_impact_batch(*, limit: int = 50, force: bool = False) -> dict:
    """Run impact synthesis for up to `limit` recent news items that don't
    yet have an `impact` block (or all of them when `force=True`).

    Cap of 50 is the daily safety limit per the operator-confirmed weekly
    cadence; even at one Gemini Flash call per item with ~$0.0003 average
    cost the run stays inside the daily ceiling.
    """
    repo = get_repository()
    items = sorted(
        repo.list(NEWS_COLLECTION),
        key=lambda r: r.get("published_at", ""),
        reverse=True,
    )
    targets = [
        i for i in items
        if force or not (i.get("impact") or {}).get("synthesised_at")
    ][:limit]
    subcaps = _load_subcaps()
    n_ok = 0
    n_err = 0
    for it in targets:
        impact = synthesise_impact(it, subcaps=subcaps)
        it["impact"] = impact
        try:
            repo.upsert(NEWS_COLLECTION, it.get("id") or it.get("news_id"), it)
            n_ok += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("impact persist failed for %s: %s", it.get("id"), exc)
            n_err += 1
    return {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "scanned": len(items),
        "synthesised": n_ok,
        "errors": n_err,
        "force": force,
    }
