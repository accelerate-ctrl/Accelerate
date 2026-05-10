"""Cloud Run Job: evidence_promotion_nightly.

Promotes raw news / story / SOW rows into the canonical
`evidence_index` collection (per spec §6 evidence registry).
Nightly cadence; idempotent — same row promoted multiple times yields
the same canonical key.

Promotion logic:
  - news_items / trends_items   → kind="external"
  - sow_mentions                → kind="internal"
  - stories_canonical           → kind="internal_story"
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..services.repository import get_repository

EVIDENCE_COLLECTION = "evidence_index"


def run() -> dict:
    repo = get_repository()
    promoted = 0
    skipped = 0
    with repo.defer_persist():
        promoted += _promote_collection(
            repo, "news_items", kind="external",
            title_field="title", id_prefix="ext-news",
        )
        promoted += _promote_collection(
            repo, "trends_items", kind="external",
            title_field="title", id_prefix="ext-trend",
        )
        promoted += _promote_collection(
            repo, "sow_mentions", kind="internal",
            title_field="excerpt", id_prefix="int-sow",
        )
        promoted += _promote_collection(
            repo, "stories_canonical", kind="internal_story",
            title_field="summary", id_prefix="int-story",
        )
    return {"promoted": promoted, "skipped": skipped, "indexed_at": datetime.now(timezone.utc).isoformat()}


def _promote_collection(repo, source: str, *, kind: str, title_field: str, id_prefix: str) -> int:
    n = 0
    for row in repo.list(source):
        rid = row.get("id") or row.get("mention_id") or row.get("story_key")
        if not rid:
            continue
        eid = f"{id_prefix}-{rid}"
        repo.upsert(
            EVIDENCE_COLLECTION,
            eid,
            {
                "id": eid,
                "kind": kind,
                "source_collection": source,
                "source_id": rid,
                "title": (row.get(title_field) or "")[:300],
                "promoted_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        n += 1
    return n
