"""Catalogue snapshot + version + diff."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .catalogue_service import list_pillars, list_subcaps
from .repository import get_repository

log = logging.getLogger(__name__)

VERSIONS_COLL = "catalogue_versions"
SNAPSHOTS_COLL = "catalogue_snapshots"  # full snapshot embedded for in-mem; pointer-only in mongo


def save_version(*, label: str | None, summary: str | None, by: str) -> dict:
    """Take a snapshot of all subcaps + pillar metadata, store with a new version_id."""
    started = datetime.utcnow()
    # Include microseconds so two saves within the same second don't
    # collide on the timestamp-based id (which previously caused the
    # second save to silently overwrite the first).
    version_id = f"v-{int(started.timestamp() * 1_000_000)}"
    pillars = list_pillars()
    subcaps = list_subcaps()
    pillar_counts = {p["pillar_id"]: 0 for p in pillars}
    for s in subcaps:
        pid = s.get("pillar_id", "?")
        pillar_counts[pid] = pillar_counts.get(pid, 0) + 1

    snapshot = {
        "version_id": version_id,
        "pillars": pillars,
        "subcaps": subcaps,
    }

    # Mark prior current=false
    repo = get_repository()
    for v in repo.list(VERSIONS_COLL, {"is_current": True}):
        v["is_current"] = False
        repo.upsert(VERSIONS_COLL, v["version_id"], v)

    snapshot_uri = _persist_snapshot(version_id, snapshot)
    version = {
        "version_id": version_id,
        "label": label,
        "summary": summary,
        "created_at": started.isoformat(),
        "created_by": by,
        "pillar_counts": pillar_counts,
        "snapshot_uri": snapshot_uri,
        "source_files": {p["pillar_id"]: {
            "file_id": p.get("source_file_id"),
            "file_name": p.get("source_file_name"),
            "modified_at": p.get("source_file_modified_at"),
            "version": p.get("source_version"),
        } for p in pillars},
        "is_current": True,
    }
    repo.upsert(VERSIONS_COLL, version_id, version)
    return version


def list_versions(limit: int = 50) -> list[dict]:
    versions = get_repository().list(VERSIONS_COLL)
    versions.sort(key=lambda v: v.get("created_at", ""), reverse=True)
    return versions[:limit]


def get_version(version_id: str) -> dict | None:
    return get_repository().get(VERSIONS_COLL, version_id)


def load_snapshot(version_id: str) -> dict | None:
    repo = get_repository()
    snap = repo.get(SNAPSHOTS_COLL, version_id)
    if snap:
        return snap
    # Try local FS fallback
    v = get_version(version_id)
    if v and v.get("snapshot_uri", "").startswith("file://"):
        path = Path(v["snapshot_uri"].removeprefix("file://"))
        if path.exists():
            return json.loads(path.read_text())
    return None


def _persist_snapshot(version_id: str, snapshot: dict) -> str:
    """Embed in repo for in-memory; later batches add GCS write for prod."""
    repo = get_repository()
    repo.upsert(SNAPSHOTS_COLL, version_id, snapshot)
    return f"repo://{SNAPSHOTS_COLL}/{version_id}"


# ─── Diff ────────────────────────────────────────────────────────────────────


def diff_versions(version_a: str, version_b: str) -> dict:
    snap_a = load_snapshot(version_a) or {"subcaps": [], "pillars": []}
    snap_b = load_snapshot(version_b) or {"subcaps": [], "pillars": []}

    a_subs = {s["sub_cap_id"]: s for s in snap_a.get("subcaps", [])}
    b_subs = {s["sub_cap_id"]: s for s in snap_b.get("subcaps", [])}

    added = sorted(set(b_subs) - set(a_subs))
    removed = sorted(set(a_subs) - set(b_subs))
    modified: list[dict] = []
    for sid in sorted(set(a_subs) & set(b_subs)):
        a, b = a_subs[sid], b_subs[sid]
        field_diffs = _shallow_diff(a, b)
        if field_diffs:
            modified.append({"sub_cap_id": sid, "fields": field_diffs})

    a_cats_set = {s.get("category_id") for s in a_subs.values() if s.get("category_id")}
    b_cats_set = {s.get("category_id") for s in b_subs.values() if s.get("category_id")}
    added_cats = sorted(b_cats_set - a_cats_set)
    removed_cats = sorted(a_cats_set - b_cats_set)

    a_counts: dict[str, int] = {}
    for s in a_subs.values():
        a_counts[s.get("pillar_id", "?")] = a_counts.get(s.get("pillar_id", "?"), 0) + 1
    b_counts: dict[str, int] = {}
    for s in b_subs.values():
        b_counts[s.get("pillar_id", "?")] = b_counts.get(s.get("pillar_id", "?"), 0) + 1
    pillar_count_deltas = {p: b_counts.get(p, 0) - a_counts.get(p, 0) for p in set(a_counts) | set(b_counts)}

    return {
        "version_a": version_a,
        "version_b": version_b,
        "added_subcaps": added,
        "removed_subcaps": removed,
        "modified_subcaps": modified,
        "added_categories": added_cats,
        "removed_categories": removed_cats,
        "pillar_count_deltas": pillar_count_deltas,
    }


def _shallow_diff(a: dict, b: dict) -> dict[str, dict[str, Any]]:
    diffs: dict[str, dict[str, Any]] = {}
    keys = set(a) | set(b)
    skip = {"pillar_id"}  # always equal by construction
    for k in keys:
        if k in skip:
            continue
        if a.get(k) != b.get(k):
            diffs[k] = {"a": a.get(k), "b": b.get(k)}
    return diffs


# ─── Phase 4.5 — admin-gated revert (App Flow J11) ───────────────────────


REVERT_LOG_COLLECTION = "version_reverts"


def preview_revert(target_version_id: str) -> dict:
    """Compute what would change if the catalogue were reverted to
    ``target_version_id``.

    Returns the diff between the *current* live catalogue and the
    target snapshot so the J11 confirmation modal can enumerate exact
    changes before the user commits.
    """
    target = get_version(target_version_id)
    if target is None:
        raise KeyError(f"version not found: {target_version_id}")
    target_snap = load_snapshot(target_version_id)
    if not target_snap:
        raise KeyError(f"snapshot missing for version: {target_version_id}")

    # Build a "current" snapshot from the live repo.
    from .catalogue_service import list_pillars, list_subcaps

    current = {
        "version_id": "live",
        "pillars": list_pillars(),
        "subcaps": list_subcaps(),
    }
    # Reuse the diff machinery by passing snapshots directly.
    diff = _diff_snapshots(current, target_snap)
    return {
        "target_version_id": target_version_id,
        "target_label": target.get("label"),
        "target_created_at": target.get("created_at"),
        "target_created_by": target.get("created_by"),
        "current_subcap_count": len(current["subcaps"]),
        "target_subcap_count": len(target_snap.get("subcaps", [])),
        "added_subcaps": diff["added_subcaps"],
        "removed_subcaps": diff["removed_subcaps"],
        "modified_subcaps": diff["modified_subcaps"],
        "pillar_count_deltas": diff["pillar_count_deltas"],
    }


def revert_to_version(
    target_version_id: str,
    *,
    by: str,
    reason: str,
) -> dict:
    """Transactional revert. Restores subcaps + pillars to the target
    snapshot, records the revert in ``version_reverts``, and stamps a
    new ``is_current=True`` version pointing at the same snapshot so
    the version history reflects the operator action.

    Per App Flow J11 the action is admin-gated at the API edge (see
    ``api/versions.py``); the service layer enforces a non-empty
    reason so audit trails always carry "why".
    """
    if not reason or not reason.strip():
        raise ValueError("revert_to_version requires a non-empty reason")
    target = get_version(target_version_id)
    if target is None:
        raise KeyError(f"version not found: {target_version_id}")
    target_snap = load_snapshot(target_version_id)
    if not target_snap:
        raise KeyError(f"snapshot missing for version: {target_version_id}")

    started = datetime.utcnow()
    preview = preview_revert(target_version_id)
    repo = get_repository()
    from .catalogue_service import COLLECTIONS

    with repo.defer_persist():
        # Wipe + re-write subcaps from the snapshot. Pillars likewise.
        for s in repo.list(COLLECTIONS["subcaps"]):
            sid = s.get("sub_cap_id")
            if sid:
                repo.delete(COLLECTIONS["subcaps"], sid)
        for s in target_snap.get("subcaps", []):
            sid = s.get("sub_cap_id")
            if sid:
                repo.upsert(COLLECTIONS["subcaps"], sid, s)
        for p in repo.list(COLLECTIONS["pillars"]):
            pid = p.get("pillar_id")
            if pid:
                repo.delete(COLLECTIONS["pillars"], pid)
        for p in target_snap.get("pillars", []):
            pid = p.get("pillar_id")
            if pid:
                repo.upsert(COLLECTIONS["pillars"], pid, p)

        # Mark every prior current=false then create a new current
        # version pointing at the restored snapshot so the version
        # timeline shows the revert as its own entry.
        for v in repo.list(VERSIONS_COLL, {"is_current": True}):
            v["is_current"] = False
            repo.upsert(VERSIONS_COLL, v["version_id"], v)

        new_version_id = f"v-revert-{int(started.timestamp())}"
        new_version = {
            "version_id": new_version_id,
            "label": f"revert→{target_version_id}",
            "summary": reason.strip(),
            "created_at": started.isoformat(),
            "created_by": by,
            "is_current": True,
            "is_revert": True,
            "reverted_to": target_version_id,
            "snapshot_uri": target.get("snapshot_uri"),
            "pillar_counts": target.get("pillar_counts"),
        }
        repo.upsert(VERSIONS_COLL, new_version_id, new_version)

        # Audit log row.
        revert_id = f"revert-{int(started.timestamp())}"
        revert_row = {
            "id": revert_id,
            "performed_at": started.isoformat(),
            "performed_by": by,
            "target_version_id": target_version_id,
            "new_version_id": new_version_id,
            "reason": reason.strip(),
            "subcap_delta": (
                preview["target_subcap_count"] - preview["current_subcap_count"]
            ),
            "added_count": len(preview["added_subcaps"]),
            "removed_count": len(preview["removed_subcaps"]),
            "modified_count": len(preview["modified_subcaps"]),
        }
        repo.upsert(REVERT_LOG_COLLECTION, revert_id, revert_row)

    log.info(
        "catalogue reverted to %s (new version %s); %d added, %d removed, %d modified",
        target_version_id, new_version_id,
        len(preview["added_subcaps"]),
        len(preview["removed_subcaps"]),
        len(preview["modified_subcaps"]),
    )
    return {
        "new_version_id": new_version_id,
        "target_version_id": target_version_id,
        "added": len(preview["added_subcaps"]),
        "removed": len(preview["removed_subcaps"]),
        "modified": len(preview["modified_subcaps"]),
        "reason": reason.strip(),
        "performed_by": by,
        "performed_at": started.isoformat(),
    }


def list_reverts(limit: int = 50) -> list[dict]:
    rows = get_repository().list(REVERT_LOG_COLLECTION)
    rows.sort(key=lambda r: r.get("performed_at") or "", reverse=True)
    return rows[:limit]


# Diff helper that operates on snapshot dicts directly (the existing
# diff_versions only accepts version ids, but the revert preview needs
# to diff against the live state which has no version id).


def _diff_snapshots(snap_a: dict, snap_b: dict) -> dict:
    a_subs = {s["sub_cap_id"]: s for s in snap_a.get("subcaps", [])}
    b_subs = {s["sub_cap_id"]: s for s in snap_b.get("subcaps", [])}
    added = sorted(set(b_subs) - set(a_subs))
    removed = sorted(set(a_subs) - set(b_subs))
    modified: list[dict] = []
    for sid in sorted(set(a_subs) & set(b_subs)):
        a, b = a_subs[sid], b_subs[sid]
        field_diffs = _shallow_diff(a, b)
        if field_diffs:
            modified.append({"sub_cap_id": sid, "fields": field_diffs})
    a_counts: dict[str, int] = {}
    for s in a_subs.values():
        a_counts[s.get("pillar_id", "?")] = a_counts.get(s.get("pillar_id", "?"), 0) + 1
    b_counts: dict[str, int] = {}
    for s in b_subs.values():
        b_counts[s.get("pillar_id", "?")] = b_counts.get(s.get("pillar_id", "?"), 0) + 1
    pillar_count_deltas = {
        p: b_counts.get(p, 0) - a_counts.get(p, 0)
        for p in set(a_counts) | set(b_counts)
    }
    return {
        "added_subcaps": added,
        "removed_subcaps": removed,
        "modified_subcaps": modified,
        "pillar_count_deltas": pillar_count_deltas,
    }
