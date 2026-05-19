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
    origin: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """List suggestions filtered by status / subcap / origin.

    Phase 4.3 — adds ``origin`` filter (loop / news / partner /
    audit / what-if) so the AI Suggestions page can group by where
    the suggestion came from. Origin defaults to ``"loop"`` for older
    rows that don't have an explicit origin field.
    """
    repo = get_repository()
    items = repo.list(SUGGESTION_COLLECTION)
    if status:
        items = [s for s in items if s.get("status") == status]
    if sub_cap_id:
        items = [s for s in items if s.get("sub_cap_id") == sub_cap_id]
    if origin:
        items = [s for s in items if (s.get("origin") or "loop") == origin]
    items.sort(key=lambda s: s.get("created_at", ""), reverse=True)
    return items[:limit]


def list_origins() -> dict[str, int]:
    """Distinct origin values currently in the suggestions collection
    plus a count per origin. Drives the FE filter chips so the page
    only renders origins that actually have rows."""
    repo = get_repository()
    out: dict[str, int] = {}
    for s in repo.list(SUGGESTION_COLLECTION):
        origin = s.get("origin") or "loop"
        out[origin] = out.get(origin, 0) + 1
    return out


def bulk_reject(
    suggestion_ids: list[str],
    actor: str,
    *,
    reason: str,
) -> dict:
    """Reject multiple pending suggestions in one call (IMP-11).

    The classic use case: a monthly cycle produced 20 low-quality
    AUTO suggestions and the pillar lead wants to clear them all
    with one rationale. Operating row-by-row is the 80% case at
    scale.

    Behaviour:
    - Skips suggestions that are not currently ``pending`` (returns
      them in ``skipped`` so the FE can show what wasn't touched).
    - Skips missing ids (returns them in ``missing``).
    - Requires non-empty ``reason`` per App Flow J3.
    """
    if not reason or not reason.strip():
        raise ValueError("bulk_reject requires a non-empty reason")
    repo = get_repository()
    now = datetime.now(timezone.utc).isoformat()
    rejected: list[dict] = []
    skipped: list[dict] = []
    missing: list[str] = []
    reason_stripped = reason.strip()
    for sid in suggestion_ids:
        sug = repo.get(SUGGESTION_COLLECTION, sid)
        if sug is None:
            missing.append(sid)
            continue
        if sug.get("status") != "pending":
            skipped.append({"id": sid, "current_status": sug.get("status")})
            continue
        updated = {
            **sug,
            "status": "rejected",
            "decided_at": now,
            "decided_by": actor,
            "reject_reason": reason_stripped,
            "bulk_rejected": True,
        }
        repo.upsert(SUGGESTION_COLLECTION, sid, updated)
        rejected.append(updated)
    return {
        "rejected_count": len(rejected),
        "skipped_count": len(skipped),
        "missing_count": len(missing),
        "rejected": rejected,
        "skipped": skipped,
        "missing": missing,
    }


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
