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
