"""Catalogue snapshot + version + diff."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from .catalogue_service import COLLECTIONS, list_pillars, list_subcaps
from .repository import get_repository

log = logging.getLogger(__name__)

VERSIONS_COLL = "catalogue_versions"
SNAPSHOTS_COLL = "catalogue_snapshots"  # full snapshot embedded for in-mem; pointer-only in mongo


def save_version(*, label: str | None, summary: str | None, by: str) -> dict:
    """Take a snapshot of all subcaps + pillar metadata, store with a new version_id."""
    started = datetime.utcnow()
    version_id = f"v-{int(started.timestamp())}"
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

    a_cats = {c["category_id"]: c for p in snap_a.get("pillars", []) for c in []}
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
