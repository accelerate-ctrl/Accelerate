"""Suggestions lifecycle: list / apply / reject.

Suggestions are produced by :mod:`consultant_loop`.  This module is the
read/transition layer the API exposes.  Applying a suggestion currently
records the transition + writes a stub diff into ``suggestion_applies``
so Batch 6 (lifecycle engine) can pick it up; the actual catalogue write
goes through the existing diff-viewer + version-service flow.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .repository import get_repository

SUGGESTION_COLLECTION = "suggestions"
APPLIES_COLLECTION = "suggestion_applies"


def list_suggestions(
    status: str | None = None,
    sub_cap_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    repo = get_repository()
    items = repo.list(SUGGESTION_COLLECTION)
    if status:
        items = [s for s in items if s.get("status") == status]
    if sub_cap_id:
        items = [s for s in items if s.get("sub_cap_id") == sub_cap_id]
    items.sort(key=lambda s: s.get("created_at", ""), reverse=True)
    return items[:limit]


def get_suggestion(sug_id: str) -> dict | None:
    return get_repository().get(SUGGESTION_COLLECTION, sug_id)


def apply_suggestion(sug_id: str, actor: str) -> dict:
    repo = get_repository()
    sug = repo.get(SUGGESTION_COLLECTION, sug_id)
    if not sug:
        raise KeyError(sug_id)
    if sug["status"] != "pending":
        raise ValueError(f"already {sug['status']}")
    now = datetime.now(timezone.utc).isoformat()
    sug = {**sug, "status": "applied", "decided_at": now, "decided_by": actor}
    repo.upsert(SUGGESTION_COLLECTION, sug_id, sug)
    repo.upsert(
        APPLIES_COLLECTION,
        f"apply-{sug_id}",
        {
            "id": f"apply-{sug_id}",
            "suggestion_id": sug_id,
            "kind": sug.get("kind"),
            "target": sug.get("target"),
            "applied_at": now,
            "applied_by": actor,
            "status": "queued_for_diff",  # Batch 6 picks this up
        },
    )
    return sug


def reject_suggestion(sug_id: str, actor: str, reason: str = "") -> dict:
    repo = get_repository()
    sug = repo.get(SUGGESTION_COLLECTION, sug_id)
    if not sug:
        raise KeyError(sug_id)
    if sug["status"] != "pending":
        raise ValueError(f"already {sug['status']}")
    now = datetime.now(timezone.utc).isoformat()
    sug = {
        **sug,
        "status": "rejected",
        "decided_at": now,
        "decided_by": actor,
        "reject_reason": reason or None,
    }
    repo.upsert(SUGGESTION_COLLECTION, sug_id, sug)
    return sug


def stats() -> dict:
    repo = get_repository()
    items = repo.list(SUGGESTION_COLLECTION)
    out = {"pending": 0, "applied": 0, "rejected": 0, "total": len(items)}
    for s in items:
        out[s.get("status", "pending")] = out.get(s.get("status", "pending"), 0) + 1
    return out
