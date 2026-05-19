"""Cross-pillar entity deduplication (Schema §5.2 / Phase 1.4).

The v7.0 workbooks include several entity kinds that are intentionally
shared across pillars — the same Offering, Data Product, L3 Platform,
or Agentforce Agent appears in P1, P2, P3, and P4 workbooks with
slightly different mapped-subcap counts. The per-pillar parser
(``sheets_parser``) emits these rows verbatim into pillar-keyed
collections; this service walks those collections and produces a single
canonical row per entity, persisted into ``canonical_entities``.

Document ID pattern (Schema §5.2): ``{entity_kind}:{canonical_id}`` —
e.g. ``Offering:OFF-DMA-Accelerator``.

The merge rule for each kind is conservative:

- Identity fields (id, name, category, status) take the first non-empty
  value seen across pillars. The v7.0 contract guarantees these are
  consistent — divergence triggers a flag.
- ``source_pillars: list[str]`` is the union of every pillar that
  contributed a row. Useful for "this offering ships in P1 + P3 but
  not P2" cross-pillar reporting.
- Numeric per-pillar fields (``total_mapped_subcaps`` etc.) are also
  exposed as a per-pillar map so the Vendor Intelligence page can
  drill into them.

Public surface:

    rebuild_canonical_entities() -> CanonicalSummary
    list_canonical(entity_kind: str) -> list[dict]
    get_canonical(entity_kind: str, canonical_id: str) -> dict | None
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from .catalogue_service import COLLECTIONS
from .repository import get_repository

logger = logging.getLogger(__name__)

CANONICAL_COLLECTION = "canonical_entities"


# ─── Entity-kind manifests ──────────────────────────────────────────────────
#
# Each entry describes how to canonicalise one entity kind:
# - ``source``: the per-pillar collection that holds the raw rows.
# - ``key``: the field on each row that identifies the canonical entity.
# - ``identity_fields``: fields whose values must be consistent across
#   pillars; divergence is flagged but the first-seen value wins.
# - ``per_pillar_numeric``: numeric fields exposed as a per-pillar map
#   instead of folded into a single number.

_ENTITY_KINDS: dict[str, dict[str, Any]] = {
    "L3Platform": {
        "source": "l3",
        "key": "l3_id",
        "identity_fields": ("name", "vendor", "category", "description", "reference_url"),
        "per_pillar_numeric": (),
    },
    "Offering": {
        "source": "offerings",
        "key": "offering_id",
        "identity_fields": (
            "offering_name", "category", "wrap_around", "status",
            "overview", "industry_challenge", "outcomes",
            "core_capabilities", "tiers", "primary_vendors",
            "reference_url",
        ),
        "per_pillar_numeric": (
            "total_mapped_subcaps", "active_mapped_subcaps", "linkage_health_pct",
        ),
    },
    "DataProduct": {
        "source": "data_products",
        "key": "module_id",
        "identity_fields": (
            "module_name", "category", "description",
            "typical_pairing", "validation_strength", "reference_url",
        ),
        "per_pillar_numeric": (
            "total_mapped_subcaps", "active_mapped_subcaps", "linkage_health_pct",
        ),
    },
    "AgentforceAgent": {
        "source": "agentforce_agents",
        "key": "agent_id",
        "identity_fields": (
            "agent_name", "lob", "workflow", "status",
            "source_type", "parent_l3", "description", "source_url",
        ),
        "per_pillar_numeric": (),
    },
}


@dataclass
class CanonicalEntity:
    """The persisted shape of one canonical row."""

    entity_kind: str
    canonical_id: str
    identity: dict[str, Any] = field(default_factory=dict)
    source_pillars: list[str] = field(default_factory=list)
    per_pillar: dict[str, dict[str, Any]] = field(default_factory=dict)
    divergence_flags: list[str] = field(default_factory=list)
    updated_at: str = ""
    schema_version_: str = "canonical-entity-v1"

    def doc_id(self) -> str:
        return f"{self.entity_kind}:{self.canonical_id}"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["_schema_version"] = d.pop("schema_version_")
        return d


@dataclass
class CanonicalSummary:
    """Result of a rebuild run."""

    started_at: str
    completed_at: str
    counts_by_kind: dict[str, int]
    divergences: list[dict[str, Any]]


# ─── Helpers ────────────────────────────────────────────────────────────────


def _first_non_empty(values: list[Any]) -> Any:
    for v in values:
        if v not in (None, "", [], {}):
            return v
    return None


def _pillar_of(row: dict) -> str:
    """Best-effort source-pillar resolution.

    Offerings + data-products carry ``source_pillar_id`` (set by the
    parser); other collections use ``pillar_id``.
    """
    return row.get("source_pillar_id") or row.get("pillar_id") or "?"


def _canonicalise_one_kind(
    entity_kind: str, manifest: dict[str, Any],
) -> tuple[list[CanonicalEntity], list[dict[str, Any]]]:
    """Build canonical entities for one kind. Returns (entities, divergences)."""
    repo = get_repository()
    coll_name = COLLECTIONS[manifest["source"]]
    rows = repo.list(coll_name)
    key_field = manifest["key"]

    grouped: dict[str, list[dict]] = {}
    for row in rows:
        cid = row.get(key_field)
        if not cid:
            continue
        grouped.setdefault(cid, []).append(row)

    out_entities: list[CanonicalEntity] = []
    divergences: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()

    for cid, pillar_rows in grouped.items():
        # Identity merge — first non-empty per field.
        identity: dict[str, Any] = {}
        flags: list[str] = []
        for f in manifest["identity_fields"]:
            seen_values = [r.get(f) for r in pillar_rows if r.get(f) not in (None, "")]
            unique = {v for v in seen_values if v is not None}
            identity[f] = _first_non_empty(seen_values)
            # If two pillars supply different non-empty values for an
            # identity field, that's worth flagging — the v7.0 contract
            # says these should be consistent.
            if len({_normalise(v) for v in unique}) > 1:
                flags.append(f"divergent identity field: {f}")
                divergences.append({
                    "entity_kind": entity_kind,
                    "canonical_id": cid,
                    "field": f,
                    "values_seen": {
                        _pillar_of(r): r.get(f) for r in pillar_rows
                        if r.get(f) not in (None, "")
                    },
                })

        per_pillar: dict[str, dict[str, Any]] = {}
        for r in pillar_rows:
            p = _pillar_of(r)
            entry = per_pillar.setdefault(p, {})
            for nf in manifest["per_pillar_numeric"]:
                v = r.get(nf)
                if v is not None:
                    entry[nf] = v

        out_entities.append(CanonicalEntity(
            entity_kind=entity_kind,
            canonical_id=cid,
            identity=identity,
            source_pillars=sorted({_pillar_of(r) for r in pillar_rows}),
            per_pillar=per_pillar,
            divergence_flags=flags,
            updated_at=now,
        ))
    return out_entities, divergences


def _normalise(v: Any) -> Any:
    """Best-effort equality normalisation so trivial whitespace
    differences don't trigger spurious divergence flags."""
    if isinstance(v, str):
        return " ".join(v.strip().split())
    return v


# ─── Public API ─────────────────────────────────────────────────────────────


def rebuild_canonical_entities() -> CanonicalSummary:
    """Walk every per-pillar source collection and rebuild the
    ``canonical_entities`` collection from scratch.

    Intended to be called after every ``catalogue_service.refresh_pillar``
    (the API endpoint wires this up in ``api/catalogue.py``). Safe to
    re-run; existing canonical rows are upserted in place.
    """
    started = datetime.now(timezone.utc)
    repo = get_repository()
    counts: dict[str, int] = {}
    all_divergences: list[dict[str, Any]] = []

    with repo.defer_persist():
        # Drop the existing canonical collection and rebuild. Cheaper
        # than diffing because the source collections already encode
        # provenance — a full rebuild is O(N) over the per-pillar rows.
        for old in repo.list(CANONICAL_COLLECTION):
            doc_id = (
                old.get("doc_id")
                or f"{old.get('entity_kind', '?')}:{old.get('canonical_id', '?')}"
            )
            repo.delete(CANONICAL_COLLECTION, doc_id)

        upserts: list[tuple[str, dict[str, Any]]] = []
        for kind, manifest in _ENTITY_KINDS.items():
            entities, divergences = _canonicalise_one_kind(kind, manifest)
            counts[kind] = len(entities)
            all_divergences.extend(divergences)
            for ent in entities:
                upserts.append((ent.doc_id(), ent.to_dict()))
        if upserts:
            repo.upsert_many(CANONICAL_COLLECTION, upserts)

    completed = datetime.now(timezone.utc)
    summary = CanonicalSummary(
        started_at=started.isoformat(),
        completed_at=completed.isoformat(),
        counts_by_kind=counts,
        divergences=all_divergences,
    )
    logger.info(
        "canonical entities rebuilt: %s (%d divergences)",
        counts, len(all_divergences),
    )
    return summary


def list_canonical(entity_kind: str | None = None) -> list[dict]:
    rows = get_repository().list(CANONICAL_COLLECTION)
    if entity_kind:
        rows = [r for r in rows if r.get("entity_kind") == entity_kind]
    return rows


def get_canonical(entity_kind: str, canonical_id: str) -> dict | None:
    return get_repository().get(CANONICAL_COLLECTION, f"{entity_kind}:{canonical_id}")


def supported_kinds() -> list[str]:
    return list(_ENTITY_KINDS.keys())


__all__ = [
    "CANONICAL_COLLECTION",
    "CanonicalEntity",
    "CanonicalSummary",
    "get_canonical",
    "list_canonical",
    "rebuild_canonical_entities",
    "supported_kinds",
]
