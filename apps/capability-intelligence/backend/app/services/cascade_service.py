"""Cascade replication for subcap toggles (PRD FR-2 / App Flow J4).

When a subcap is toggled Inactive, the v7.0 workbook implements the
governance cascade through ``XLOOKUP`` formulas in 10+ tabs. This service
replicates that behavior in the application so the user's mental model
holds: flipping ``Zennify_Status`` on a subcap fans out across every
dependent surface.

Two entry points:

- :func:`preview` enumerates *what would change* without writing anything.
  Used by the cascade preview modal in J4 to disclose downstream impact
  before the user commits.
- :func:`apply` performs the cascade as a single transactional batch via
  :meth:`Repository.defer_persist`, so the user never sees a half-toggled
  state. Returns the same report the preview would have produced, plus
  the applied flag.

Affected collections (v7.0 schema reference):

- ``subcaps`` (2_Capability_Map)
- ``stories`` (3_User_Stories_Catalogue)
- ``l4_features`` (5_L4_Detailed_Features, cascade col P)
- ``maturity_descriptors`` (6_Maturity_Descriptors, cascade col O)
- ``theme_mappings`` (15_Theme_SubCap_Mapping, cascade col G)
- ``vc_mappings`` (21_VC_Mapping_PerSubcap)
- ``completeness`` (18_SubCap_Completeness_Profile) — when present
- ``cross_pillar_stories`` (14_CrossPillar_Stories) — when present
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from .catalogue_service import COLLECTIONS
from .repository import get_repository

logger = logging.getLogger(__name__)

CASCADE_LOG_COLLECTION = "cascade_runs"

# How each downstream collection links back to a subcap. ``subcap_field``
# names the column that carries the ``sub_cap_id`` reference; ``label`` is
# the human-readable name surfaced in the preview modal.
_CASCADE_TARGETS: list[dict[str, str]] = [
    {"key": "stories", "subcap_field": "sub_cap_id", "label": "User stories"},
    {"key": "l4", "subcap_field": "sub_cap_id", "label": "L4 features"},
    {"key": "maturity", "subcap_field": "sub_cap_id", "label": "Maturity descriptors"},
    {"key": "themes", "subcap_field": "sub_cap_id", "label": "Theme mappings"},
    {"key": "vc_mappings", "subcap_field": "sub_cap_id", "label": "Value-chain mappings"},
    {"key": "use_cases", "subcap_field": "sub_cap_id", "label": "Use cases"},
]

# Optional collections that may or may not be populated depending on
# which v7.0 tabs the parser has caught up to. Missing collections are
# silently skipped — they contribute 0 to the cascade.
_OPTIONAL_TARGETS: list[dict[str, str]] = [
    {"key": "completeness", "subcap_field": "sub_cap_id", "label": "Completeness profile"},
    {"key": "cross_pillar_stories", "subcap_field": "sub_cap_id", "label": "Cross-pillar stories"},
]


@dataclass
class TargetImpact:
    """Per-collection impact summary."""

    label: str
    collection: str
    count: int
    sample_ids: list[str] = field(default_factory=list)


@dataclass
class CascadeReport:
    """Preview or post-apply summary of a cascade run."""

    sub_cap_id: str
    sub_cap_name: str
    from_status: str | None
    to_status: str
    reason: str | None
    targets: list[TargetImpact]
    total_rows_affected: int
    applied: bool
    started_at: str
    completed_at: str
    run_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            **{k: v for k, v in asdict(self).items() if k != "targets"},
            "targets": [asdict(t) for t in self.targets],
        }


# ─── Helpers ────────────────────────────────────────────────────────────────


def _collection_name(key: str) -> str | None:
    """Look up a logical collection key in the catalogue COLLECTIONS map.

    Returns ``None`` for keys that aren't currently registered (typically
    the optional v7.0-only collections that don't yet exist).
    """
    return COLLECTIONS.get(key)


def _sample_ids(docs: list[dict], n: int = 5) -> list[str]:
    """Best-effort identifier sample for the preview UI."""
    out: list[str] = []
    for d in docs[:n]:
        for field_name in ("story_key", "id", "doc_id", "feature_name", "theme_name"):
            v = d.get(field_name)
            if v:
                out.append(str(v))
                break
        else:
            # No obvious ID — fall back to a stable hash-friendly fragment
            out.append(d.get("sub_cap_id", "?"))
    return out


def _scan_targets(
    sub_cap_id: str,
    *,
    include_optional: bool = True,
) -> list[TargetImpact]:
    """List downstream rows linked to a subcap, by target collection."""
    repo = get_repository()
    impacts: list[TargetImpact] = []
    targets = list(_CASCADE_TARGETS)
    if include_optional:
        targets.extend(_OPTIONAL_TARGETS)

    for t in targets:
        coll = _collection_name(t["key"])
        if coll is None:
            continue
        try:
            rows = repo.list(coll, {t["subcap_field"]: sub_cap_id})
        except Exception:
            logger.exception("cascade: scan failed for %s (%s)", t["key"], coll)
            continue
        if not rows:
            continue
        impacts.append(
            TargetImpact(
                label=t["label"],
                collection=coll,
                count=len(rows),
                sample_ids=_sample_ids(rows),
            )
        )
    return impacts


def _resolve_subcap(sub_cap_id: str) -> dict | None:
    return get_repository().get(COLLECTIONS["subcaps"], sub_cap_id)


# ─── Public API ─────────────────────────────────────────────────────────────


def preview(sub_cap_id: str, *, to_status: str = "Inactive") -> CascadeReport:
    """Enumerate downstream rows that would be affected by toggling
    ``sub_cap_id`` to ``to_status`` — without writing anything.

    Used by the J4 cascade preview modal.
    """
    started = datetime.now(timezone.utc)
    subcap = _resolve_subcap(sub_cap_id)
    if subcap is None:
        raise KeyError(f"subcap not found: {sub_cap_id}")

    targets = _scan_targets(sub_cap_id)
    total = sum(t.count for t in targets)
    completed = datetime.now(timezone.utc)
    return CascadeReport(
        sub_cap_id=sub_cap_id,
        sub_cap_name=subcap.get("sub_cap_name", sub_cap_id),
        from_status=subcap.get("zennify_status"),
        to_status=to_status,
        reason=None,
        targets=targets,
        total_rows_affected=total,
        applied=False,
        started_at=started.isoformat(),
        completed_at=completed.isoformat(),
    )


def apply(
    sub_cap_id: str,
    *,
    to_status: str = "Inactive",
    reason: str,
    by: str = "system",
) -> CascadeReport:
    """Apply a subcap status toggle and cascade to every dependent row.

    ``reason`` is required — App Flow J4 mandates an explicit rationale so
    the audit trail captures *why* a subcap was deactivated.

    The toggle is transactional: every write happens inside a single
    :meth:`Repository.defer_persist` block so the persisted catalogue
    never reflects a half-applied state. The cascade run itself is logged
    to ``cascade_runs/{run_id}`` for the audit trail.
    """
    if not reason or not reason.strip():
        raise ValueError("cascade.apply requires a non-empty reason")

    started = datetime.now(timezone.utc)
    repo = get_repository()
    subcap = _resolve_subcap(sub_cap_id)
    if subcap is None:
        raise KeyError(f"subcap not found: {sub_cap_id}")

    from_status = subcap.get("zennify_status")
    targets = _scan_targets(sub_cap_id)

    # The cascade field name varies per collection in the v7.0 workbook
    # (col Q on stories, col P on l4, col O on maturity, etc.). We
    # normalize on a single ``cascade_status`` field that mirrors the
    # subcap's new status — downstream consumers read this field
    # regardless of which tab originated it.
    cascade_status = to_status

    with repo.defer_persist():
        # 1) The subcap itself
        updated = {**subcap, "zennify_status": to_status, "cascade_status": cascade_status}
        repo.upsert(COLLECTIONS["subcaps"], sub_cap_id, updated)

        # 2) Each downstream collection
        for t in _CASCADE_TARGETS + _OPTIONAL_TARGETS:
            coll = _collection_name(t["key"])
            if coll is None:
                continue
            rows = repo.list(coll, {t["subcap_field"]: sub_cap_id})
            if not rows:
                continue
            updates: list[tuple[str, dict]] = []
            for row in rows:
                # Each row keeps its native primary key; we touch only the
                # cascade flag. ``_doc_id_for_row`` falls back to a stable
                # composite when no native ID is present.
                doc_id = _doc_id_for_row(t["key"], row)
                if doc_id is None:
                    continue
                updates.append((doc_id, {**row, "cascade_status": cascade_status}))
            if updates:
                repo.upsert_many(coll, updates)

    completed = datetime.now(timezone.utc)
    total = sum(t.count for t in targets)
    run_id = f"cascade-{int(started.timestamp())}-{sub_cap_id}"
    report = CascadeReport(
        sub_cap_id=sub_cap_id,
        sub_cap_name=subcap.get("sub_cap_name", sub_cap_id),
        from_status=from_status,
        to_status=to_status,
        reason=reason.strip(),
        targets=targets,
        total_rows_affected=total,
        applied=True,
        started_at=started.isoformat(),
        completed_at=completed.isoformat(),
        run_id=run_id,
    )
    repo.upsert(CASCADE_LOG_COLLECTION, run_id, {**report.to_dict(), "by": by})
    logger.info(
        "cascade applied: subcap=%s from=%s to=%s rows=%d by=%s",
        sub_cap_id, from_status, to_status, total, by,
    )
    return report


def _doc_id_for_row(target_key: str, row: dict) -> str | None:
    """Resolve a row's document identifier for the given collection.

    Each target has its own natural primary key; this helper centralizes
    the lookup so ``apply`` doesn't grow a per-key switch. Returns
    ``None`` if no usable ID exists (the row will be skipped from the
    cascade — those rows show up in QA as orphans).
    """
    if target_key == "stories":
        return row.get("story_key") or row.get("id")
    if target_key == "l4":
        sc = row.get("sub_cap_id")
        l3 = row.get("l3_platform_id") or ""
        feat = row.get("feature_name") or row.get("feature_slug") or ""
        if sc and feat:
            return f"{sc}__{l3}__{feat}"
        return row.get("id")
    if target_key == "maturity":
        return row.get("sub_cap_id")
    if target_key == "themes":
        theme = row.get("theme_name") or row.get("theme")
        sub = row.get("sub_cap_id")
        if theme and sub:
            return f"{theme}::{sub}"
        return row.get("id")
    if target_key == "vc_mappings":
        sc = row.get("sub_cap_id")
        sv = row.get("subvertical") or row.get("subvertical_code")
        if sc and sv:
            return f"{sc}__{sv}"
        return row.get("id")
    if target_key == "use_cases":
        return row.get("use_case_id") or row.get("id")
    if target_key == "completeness":
        return row.get("sub_cap_id")
    if target_key == "cross_pillar_stories":
        return row.get("story_key") or row.get("id")
    return row.get("id")


def list_runs(limit: int = 50) -> list[dict]:
    """Recent cascade runs for the audit dashboard."""
    rows = get_repository().list(CASCADE_LOG_COLLECTION)
    rows.sort(key=lambda r: r.get("started_at") or "", reverse=True)
    return rows[:limit]
