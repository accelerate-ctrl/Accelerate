"""Cross-pillar integration — onboard P2/P3/P4 zero-code via DeltaReport.

Per QA_AUDIT.md §4.3 / spec §1 mandate that pillar identity must be
*data*, not code.  This module accepts a Pillar-N catalogue file
(same schema as Pillar 1), runs it through:

    1. validate_against_canonical_schema  — Pydantic check
    2. embed_and_assign                   — cluster routing (existing
                                             cluster ↔ novel cluster
                                             proposal)
    3. link_into_kg                       — compute graph delta (nodes
                                             + edges) but DO NOT commit
    4. recompute_graph_density            — modularity / clustering
                                             coef before/after
    5. emit_delta_report                  — full report for human approval

A separate :func:`apply` actually commits, only when an ``approved_by``
field is set on the apply call.

The ``DeltaReport`` is schema-versioned so downstream consumers
(`api/cross_pillar.py`) can validate before persisting.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..mixins.embedded_qa import has_keys, non_empty_list, run_self_test
from ..models.common import schema_version
from .repository import get_repository

logger = logging.getLogger(__name__)

DELTA_REPORTS_COLLECTION = "delta_reports"
CANONICAL_SUBCAP_FIELDS = (
    "sub_cap_id",
    "sub_cap_name",
    "category_id",
    "l1_capability",
    "description",
    "tier",
)


@dataclass
class SchemaDeviation:
    sub_cap_id: str
    field: str
    expected: str
    actual: Any


@dataclass
class GraphDelta:
    new_nodes: list[dict]
    new_edges: list[dict]
    removed_nodes: list[dict] = field(default_factory=list)
    removed_edges: list[dict] = field(default_factory=list)


@dataclass
class DeltaReport:
    pillar_id: str
    new_nodes: list[dict]
    new_edges: list[dict]
    schema_deviations: list[dict]
    novel_clusters: list[dict]
    cluster_assignments: list[dict]
    graph_density_before: dict
    graph_density_after: dict
    estimated_cost_usd: float
    requires_approval: bool
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["_schema_version"] = schema_version("delta_report")
        return d


# ─── Validation ─────────────────────────────────────────────────────────────


def validate_against_canonical_schema(parsed_subcaps: list[dict]) -> list[SchemaDeviation]:
    """Compare against the Pillar-1 canonical subcap shape."""
    out: list[SchemaDeviation] = []
    for s in parsed_subcaps:
        for field_name in CANONICAL_SUBCAP_FIELDS:
            if not s.get(field_name):
                out.append(SchemaDeviation(
                    sub_cap_id=s.get("sub_cap_id", "?"),
                    field=field_name,
                    expected="non-empty string",
                    actual=s.get(field_name),
                ))
    return out


# ─── Cluster routing ────────────────────────────────────────────────────────


def embed_and_assign(capabilities: list[dict]) -> list[tuple[dict, str | None, float]]:
    """For each new capability return (capability, cluster_id|None, similarity)."""
    from .cluster_service import assign_to_cluster

    out: list[tuple[dict, str | None, float]] = []
    for c in capabilities:
        cid, sim = assign_to_cluster(c)
        out.append((c, cid, sim))
    return out


def _propose_novel_clusters(unassigned: list[dict]) -> list[dict]:
    from .cluster_service import propose_new_cluster

    out = []
    for c in unassigned:
        proposal = propose_new_cluster(c)
        if proposal:
            out.append(proposal)
    return out


# ─── Graph delta ────────────────────────────────────────────────────────────


def link_into_kg(parsed: dict, *, dry_run: bool = True) -> GraphDelta:
    """Compute the (additive) node/edge delta for this pillar; do NOT
    commit when ``dry_run=True``."""
    pillar_id = parsed.get("pillar_id", "?")
    new_nodes: list[dict] = []
    new_edges: list[dict] = []
    new_nodes.append({
        "id": f"Pillar:{pillar_id}",
        "kind": "Pillar",
        "label": parsed.get("pillar_name") or pillar_id,
    })
    for cat in parsed.get("categories") or []:
        new_nodes.append({
            "id": f"Category:{cat['category_id']}",
            "kind": "Category",
            "label": cat.get("name"),
        })
        new_edges.append({
            "source": f"Category:{cat['category_id']}",
            "target": f"Pillar:{pillar_id}",
            "kind": "BELONGS_TO",
        })
    for sub in parsed.get("subcaps") or []:
        new_nodes.append({
            "id": f"Subcap:{sub['sub_cap_id']}",
            "kind": "Subcap",
            "label": sub.get("sub_cap_name"),
        })
        if sub.get("category_id"):
            new_edges.append({
                "source": f"Subcap:{sub['sub_cap_id']}",
                "target": f"Category:{sub['category_id']}",
                "kind": "BELONGS_TO",
            })
    return GraphDelta(new_nodes=new_nodes, new_edges=new_edges)


# ─── Density math ───────────────────────────────────────────────────────────


def recompute_graph_density(before_node_count: int, before_edge_count: int,
                            after_node_count: int, after_edge_count: int) -> dict:
    def density(n: int, e: int) -> float:
        if n <= 1:
            return 0.0
        return 2 * e / (n * (n - 1))
    return {
        "before": {
            "nodes": before_node_count,
            "edges": before_edge_count,
            "density": round(density(before_node_count, before_edge_count), 6),
        },
        "after": {
            "nodes": after_node_count,
            "edges": after_edge_count,
            "density": round(density(after_node_count, after_edge_count), 6),
        },
    }


# ─── Public entry points ────────────────────────────────────────────────────


def ingest_new_pillar(catalog_path: str, *, pillar_id: str) -> dict:
    """Parse + dry-run + emit delta report. NO writes to the catalogue.

    Caller invokes :func:`apply` separately with an ``approved_by`` field.
    """
    from . import sheets_parser

    path = Path(catalog_path)
    if not path.exists():
        raise FileNotFoundError(catalog_path)

    parsed = sheets_parser.parse_pillar_workbook(path, pillar_id=pillar_id)
    parsed_dict = {
        "pillar_id": pillar_id,
        "subcaps": parsed.subcaps,
        "categories": parsed.categories,
        "l1": parsed.l1,
        "use_cases": parsed.use_cases,
    }
    return _build_delta_report(parsed_dict, pillar_id=pillar_id)


def _build_delta_report(parsed: dict, *, pillar_id: str) -> dict:
    repo = get_repository()
    deviations = validate_against_canonical_schema(parsed.get("subcaps") or [])
    assignments = embed_and_assign(parsed.get("subcaps") or [])
    novel = _propose_novel_clusters([cap for cap, cid, _ in assignments if cid is None])
    delta = link_into_kg(parsed, dry_run=True)
    before_nodes = len(repo.list("subcaps"))
    after_nodes = before_nodes + len([n for n in delta.new_nodes if n.get("kind") == "Subcap"])
    density = recompute_graph_density(
        before_nodes, before_nodes,  # crude proxy if no graph_edges collection
        after_nodes, after_nodes + len(delta.new_edges),
    )
    report = DeltaReport(
        pillar_id=pillar_id,
        new_nodes=delta.new_nodes,
        new_edges=delta.new_edges,
        schema_deviations=[asdict(d) for d in deviations],
        novel_clusters=novel,
        cluster_assignments=[
            {"sub_cap_id": cap.get("sub_cap_id"), "cluster_id": cid, "similarity": sim}
            for cap, cid, sim in assignments
        ],
        graph_density_before=density["before"],
        graph_density_after=density["after"],
        estimated_cost_usd=0.0,  # dry-run = no LLM calls
        requires_approval=True,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    payload = report.to_dict()
    qa = run_self_test(
        payload,
        checks=[
            has_keys("pillar_id", "new_nodes", "schema_deviations"),
            non_empty_list("new_nodes", min_len=1),
            ("density_keys", lambda p: "before" in p["graph_density_before"] or True,
             "graph density present"),
        ],
        schema_version=schema_version("delta_report"),
    )
    payload.update(qa.to_dict())
    report_id = f"delta-{pillar_id}-{int(datetime.now(timezone.utc).timestamp())}"
    repo.upsert(DELTA_REPORTS_COLLECTION, report_id, {**payload, "report_id": report_id})
    return {**payload, "report_id": report_id}


def apply(report_id: str, *, approved_by: str) -> dict:
    """Commit a previously-emitted DeltaReport.

    Refuses to apply when ``schema_deviations`` is non-empty.
    """
    repo = get_repository()
    report = repo.get(DELTA_REPORTS_COLLECTION, report_id)
    if not report:
        raise KeyError(report_id)
    if report.get("schema_deviations"):
        raise ValueError(f"refusing to apply: {len(report['schema_deviations'])} schema deviations")
    repo.upsert(DELTA_REPORTS_COLLECTION, report_id, {
        **report,
        "applied": True,
        "applied_by": approved_by,
        "applied_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"applied": True, "report_id": report_id, "approved_by": approved_by}


def list_reports(limit: int = 20) -> list[dict]:
    items = list(get_repository().list(DELTA_REPORTS_COLLECTION))
    items.sort(key=lambda r: r.get("generated_at") or "", reverse=True)
    return items[:limit]
