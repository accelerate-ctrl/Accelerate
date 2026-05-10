"""Knowledge graph builder + algorithm runner.

Batch 2 ships these node types:
  Pillar, Category, L1_Capability, Subcap, UseCase, UC_Tag,
  L3_Platform, L4_Feature, Theme, MaturityDescriptor,
  Subvertical, Cluster, VC_Stage, Persona

And these edge types:
  BELONGS_TO, USES_PLATFORM, DELIVERED_BY, SUPPORTS_UC, TAGGED_AS,
  HAS_MATURITY, REFERENCES_THEME, MAPS_TO_STAGE, IN_CLUSTER,
  IN_SUBVERTICAL, APPLIES_TO, CONSUMED_BY

The remaining 14 node types and 30+ edge types from spec §8 land in later
batches (SOWs/projects/clients/vendors/news/filings/benchmarks/etc).

Graph is held in memory, lazily built per snapshot, cached LRU(8) keyed by
the underlying repo's "version-stamp" (current ingest_run_id). Re-builds on
every catalogue refresh; no incremental edits in Batch 2.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import networkx as nx
import yaml

from . import catalogue_service as cat
from .repository import get_repository

log = logging.getLogger(__name__)


# ─── Config loading ──────────────────────────────────────────────────────────


_CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"


def _load_yaml(name: str) -> dict:
    p = _CONFIG_DIR / name
    return yaml.safe_load(p.read_text()) if p.exists() else {}


def _load_subverticals() -> list[dict]:
    return _load_yaml("subverticals.yml").get("subverticals", [])


def _load_vcc_clusters() -> list[dict]:
    return _load_yaml("vcc_clusters.yml").get("clusters", [])


def _load_uc_tag_families() -> list[dict]:
    return _load_yaml("uc_tag_families.yml").get("families", [])


# ─── VCC classifier ──────────────────────────────────────────────────────────


def classify_stage(stage_name: str, clusters: list[dict] | None = None) -> str:
    """Return VCC code (VCC-01..08) for a raw stage name; VCC-00 if no match."""
    clusters = clusters or _load_vcc_clusters()
    s = (stage_name or "").lower()
    for c in clusters:
        if c["code"] == "VCC-00":
            continue
        for kw in c.get("keywords", []):
            if kw.lower() in s:
                return c["code"]
    return "VCC-00"


# ─── UC tag extraction ───────────────────────────────────────────────────────


_UC_TAG_RX = re.compile(r"\[([A-Z][A-Z0-9_]+)\]")


def extract_uc_tag(label_or_string: str | None) -> str | None:
    if not label_or_string:
        return None
    m = _UC_TAG_RX.search(label_or_string)
    return m.group(1) if m else None


def family_for_tag(tag: str, families: list[dict] | None = None) -> str | None:
    families = families or _load_uc_tag_families()
    for fam in families:
        if tag in fam.get("tags", []):
            return fam["id"]
    return None


# ─── Builder ─────────────────────────────────────────────────────────────────


@dataclass
class GraphSummary:
    snapshot_id: str
    nodes_total: int
    edges_total: int
    nodes_by_type: dict[str, int] = field(default_factory=dict)
    edges_by_type: dict[str, int] = field(default_factory=dict)


def _current_snapshot_id() -> str:
    runs = cat.list_ingest_runs(limit=1)
    return runs[0]["run_id"] if runs else "no-ingest"


def build_graph(snapshot_id: str | None = None) -> nx.MultiDiGraph:
    """Build (or fetch from cache) the in-memory KG for a snapshot."""
    sid = snapshot_id or _current_snapshot_id()
    return _build_cached(sid)


@lru_cache(maxsize=8)
def _build_cached(snapshot_id: str) -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()

    subverticals = _load_subverticals()
    clusters = _load_vcc_clusters()
    families = _load_uc_tag_families()

    # ─── Cross-cutting reference nodes ─────────────────────────────────────
    for c in clusters:
        g.add_node(_nid("Cluster", c["code"]), kind="Cluster", code=c["code"], name=c["name"], color=c.get("color"))
    for sv in subverticals:
        g.add_node(_nid("Subvertical", sv["code"]), kind="Subvertical", code=sv["code"], name=sv["name"])
    seen_uc_tags: set[str] = set()

    # ─── Catalogue spine ───────────────────────────────────────────────────
    # L3 platforms FIRST so subcap → L3 add_edge calls don't auto-create
    # placeholder nodes with no `kind`. Some L3 IDs may still be referenced
    # without a corresponding row in 4_L3_Detailed; we backfill kind below.
    for plat in cat.list_l3():
        pid = _nid("L3_Platform", plat["l3_id"])
        g.add_node(pid, kind="L3_Platform", **_safe(plat))

    for p in cat.list_pillars():
        g.add_node(_nid("Pillar", p["pillar_id"]), kind="Pillar", **_safe(p))
    for c in cat.list_categories():
        g.add_node(_nid("Category", c["category_id"]), kind="Category", **_safe(c))
        g.add_edge(_nid("Category", c["category_id"]), _nid("Pillar", c["pillar_id"]), key="BELONGS_TO", kind="BELONGS_TO")
    for l1 in cat.list_l1():
        nid = _nid("L1_Capability", l1["l1_id"])
        g.add_node(nid, kind="L1_Capability", **_safe(l1))
        g.add_edge(nid, _nid("Category", l1["category_id"]), key="BELONGS_TO", kind="BELONGS_TO")
    for s in cat.list_subcaps():
        nid = _nid("Subcap", s["sub_cap_id"])
        g.add_node(nid, kind="Subcap", **_safe(s))
        g.add_edge(nid, _nid("Category", s["category_id"]), key="BELONGS_TO", kind="BELONGS_TO")
        # Subcap → L3 (USES_PLATFORM). l3 strings here may be free-form; match
        # on the bracketed L3 ID first. If the L3 wasn't in the platform sheet,
        # we materialize a stub node with kind set so it isn't `?`.
        for l3_str in s.get("l3_platforms", []) or []:
            m = re.search(r"\[(L3-[A-Za-z0-9_-]+)\]", str(l3_str))
            if not m:
                continue
            l3_id = m.group(1)
            l3_nid = _nid("L3_Platform", l3_id)
            if l3_nid not in g:
                g.add_node(l3_nid, kind="L3_Platform", l3_id=l3_id, name=l3_id, source="referenced_only")
            g.add_edge(nid, l3_nid, key=f"USES:{l3_id}", kind="USES_PLATFORM")
        # Personas
        for persona in s.get("personas", []) or []:
            persona = persona.strip()
            if not persona:
                continue
            pid = _nid("Persona", persona)
            if pid not in g:
                g.add_node(pid, kind="Persona", name=persona)
            g.add_edge(nid, pid, key=f"CONSUMED_BY:{persona}", kind="CONSUMED_BY")

    # L4 features
    for f in cat.list_l4():
        fid = _nid("L4_Feature", f"{f.get('sub_cap_id')}::{f.get('l3_platform_id')}::{f.get('feature_name')}")
        g.add_node(fid, kind="L4_Feature", **_safe(f))
        if f.get("sub_cap_id"):
            g.add_edge(_nid("Subcap", f["sub_cap_id"]), fid, key="USES_FEATURE", kind="USES_FEATURE")
        if f.get("l3_platform_id"):
            g.add_edge(fid, _nid("L3_Platform", f["l3_platform_id"]), key="DELIVERED_BY", kind="DELIVERED_BY")

    # Use cases + UC tags
    for uc in cat.list_use_cases():
        ucid = _nid("UseCase", uc["use_case_id"])
        g.add_node(ucid, kind="UseCase", **_safe(uc))
        if uc.get("sub_cap_id"):
            g.add_edge(_nid("Subcap", uc["sub_cap_id"]), ucid, key="SUPPORTS_UC", kind="SUPPORTS_UC")
        tag = uc.get("label") or extract_uc_tag(uc.get("description"))
        if tag:
            tag_nid = _nid("UC_Tag", tag)
            if tag not in seen_uc_tags:
                fam = family_for_tag(tag, families)
                g.add_node(tag_nid, kind="UC_Tag", code=tag, family=fam)
                seen_uc_tags.add(tag)
            g.add_edge(ucid, tag_nid, key="TAGGED_AS", kind="TAGGED_AS")

    # Themes
    for t in cat.list_themes():
        theme_nid = _nid("Theme", t.get("theme") or "?")
        if theme_nid not in g:
            g.add_node(theme_nid, kind="Theme", name=t.get("theme"))
        if t.get("sub_cap_id"):
            g.add_edge(_nid("Subcap", t["sub_cap_id"]), theme_nid, key="REFERENCES_THEME", kind="REFERENCES_THEME")

    # Maturity descriptors
    for m in cat.list_maturity():
        if not m.get("sub_cap_id"):
            continue
        for level in ("m1", "m2", "m3", "m4", "m5"):
            if not m.get(level):
                continue
            md_nid = _nid("MaturityDescriptor", f"{m['sub_cap_id']}::{level.upper()}")
            g.add_node(md_nid, kind="MaturityDescriptor", sub_cap_id=m["sub_cap_id"], level=level.upper(), descriptor=m[level])
            g.add_edge(_nid("Subcap", m["sub_cap_id"]), md_nid, key=f"HAS_MATURITY:{level}", kind="HAS_MATURITY", level=level.upper())

    # VC stages + cluster + subvertical edges
    seen_stages: dict[tuple[str, str], str] = {}  # (subvertical_code, stage_name) -> stage_nid
    for vc in cat.list_vc_mappings():
        sid = vc.get("sub_cap_id")
        sv = vc.get("subvertical_code")
        if not sid or not sv:
            continue
        # Subcap APPLIES_TO Subvertical
        g.add_edge(_nid("Subcap", sid), _nid("Subvertical", sv), key=f"APPLIES_TO:{sv}", kind="APPLIES_TO")
        for stage in vc.get("stages", []):
            key = (sv, stage)
            if key not in seen_stages:
                stage_nid = _nid("VC_Stage", f"{sv}::{stage}")
                cluster_code = classify_stage(stage, clusters)
                g.add_node(stage_nid, kind="VC_Stage", subvertical_code=sv, name=stage, cluster=cluster_code)
                g.add_edge(stage_nid, _nid("Subvertical", sv), key="IN_SUBVERTICAL", kind="IN_SUBVERTICAL")
                g.add_edge(stage_nid, _nid("Cluster", cluster_code), key="IN_CLUSTER", kind="IN_CLUSTER")
                seen_stages[key] = stage_nid
            g.add_edge(_nid("Subcap", sid), seen_stages[key], key=f"MAPS_TO_STAGE:{sv}", kind="MAPS_TO_STAGE")

    # Per QA_AUDIT.md fix #11 — extend the KG with the spec node types
    # added in Batches 3-7. Each addition is best-effort: if the
    # underlying collection is empty the loop is a no-op.
    repo = get_repository()

    # Vendor + Event nodes (Batch 6)
    for v in repo.list("vendor_profiles"):
        nid = _nid("Vendor", v.get("vendor_id") or v.get("name") or "?")
        if nid in g:
            continue
        g.add_node(nid, kind="Vendor", name=v.get("name"),
                   category=v.get("category"),
                   companies=v.get("companies") or [])
    for e in repo.list("vendor_events"):
        eid = _nid("Event", e.get("id") or "?")
        g.add_node(eid, kind="Event", title=e.get("title"),
                   source=e.get("source"), kind_of_event=e.get("kind"))
        v_nid = _nid("Vendor", e.get("vendor_id") or "?")
        if v_nid in g:
            g.add_edge(eid, v_nid, key="ABOUT_VENDOR", kind="ABOUT_VENDOR")

    # Benchmark distribution nodes (Batch 5)
    for d in repo.list("benchmark_distributions"):
        nid = _nid("Benchmark", d.get("id") or "?")
        g.add_node(nid, kind="Benchmark",
                   metric_id=d.get("metric_id"),
                   cohort_id=d.get("cohort_id"),
                   verdict=d.get("verdict"))

    # Suggestion + ReasoningChain + AuditFinding nodes (Batches 4 + 7)
    for s in repo.list("suggestions"):
        sid = _nid("Suggestion", s.get("id") or "?")
        g.add_node(sid, kind="Suggestion",
                   target=s.get("target"), status=s.get("status"))
        if s.get("chain_id"):
            g.add_edge(sid, _nid("ReasoningChain", s["chain_id"]),
                       key="PRODUCED_BY", kind="PRODUCED_BY")
        if s.get("sub_cap_id"):
            sc_nid = _nid("Subcap", s["sub_cap_id"])
            if sc_nid in g:
                g.add_edge(sid, sc_nid, key="TARGETS",
                           kind="TARGETS")

    for c in repo.list("reasoning_chains"):
        nid = _nid("ReasoningChain", c.get("chain_id") or "?")
        g.add_node(nid, kind="ReasoningChain",
                   overall=c.get("overall"),
                   cost_usd=c.get("total_cost_usd"))

    for r in repo.list("audit_reports"):
        nid = _nid("AuditFinding", r.get("report_id") or "?")
        g.add_node(nid, kind="AuditFinding",
                   summary=r.get("summary"),
                   findings_count=len(r.get("findings") or []))

    log.info("kg built snapshot=%s nodes=%d edges=%d kinds=%d/%d",
             snapshot_id, g.number_of_nodes(), g.number_of_edges(),
             len({d.get('kind') for _, d in g.nodes(data=True)}),
             len({d.get('kind') for _, _, d in g.edges(data=True)}))
    return g


def invalidate_cache() -> None:
    _build_cached.cache_clear()


def summary() -> GraphSummary:
    g = build_graph()
    by_kind: dict[str, int] = {}
    for _, attrs in g.nodes(data=True):
        by_kind[attrs.get("kind", "?")] = by_kind.get(attrs.get("kind", "?"), 0) + 1
    by_edge: dict[str, int] = {}
    for _, _, attrs in g.edges(data=True):
        k = attrs.get("kind", "?")
        by_edge[k] = by_edge.get(k, 0) + 1
    return GraphSummary(
        snapshot_id=_current_snapshot_id(),
        nodes_total=g.number_of_nodes(),
        edges_total=g.number_of_edges(),
        nodes_by_type=by_kind,
        edges_by_type=by_edge,
    )


# ─── Read API ────────────────────────────────────────────────────────────────


def export_for_render(node_kinds: list[str] | None = None, max_nodes: int = 2000) -> dict:
    """Cytoscape-ready elements: nodes + edges with style hints."""
    g = build_graph()
    nodes_out = []
    edges_out = []
    selected_ids: set[str] = set()
    for n, attrs in g.nodes(data=True):
        if node_kinds and attrs.get("kind") not in node_kinds:
            continue
        if len(selected_ids) >= max_nodes:
            break
        selected_ids.add(n)
        nodes_out.append({
            "data": {
                "id": n,
                "label": attrs.get("name") or attrs.get("sub_cap_name") or attrs.get("code") or n,
                "kind": attrs.get("kind"),
                **{k: v for k, v in attrs.items() if k != "kind"},
            }
        })
    for u, v, attrs in g.edges(data=True):
        if u not in selected_ids or v not in selected_ids:
            continue
        edges_out.append({
            "data": {
                "id": f"{u}->{v}::{attrs.get('kind')}",
                "source": u,
                "target": v,
                "kind": attrs.get("kind"),
            }
        })
    return {"nodes": nodes_out, "edges": edges_out, "truncated": len(g.nodes) > len(selected_ids)}


def neighborhood(node_id: str, hops: int = 1) -> dict:
    g = build_graph()
    if node_id not in g:
        return {"nodes": [], "edges": []}
    ids = {node_id}
    frontier = {node_id}
    for _ in range(max(0, hops)):
        next_frontier: set[str] = set()
        for n in frontier:
            for nbr in g.successors(n):
                next_frontier.add(nbr)
            for nbr in g.predecessors(n):
                next_frontier.add(nbr)
        next_frontier -= ids
        ids |= next_frontier
        frontier = next_frontier
    sub = g.subgraph(ids).copy()
    return _to_payload(sub)


def shortest_path(source: str, target: str) -> dict:
    g = build_graph()
    if source not in g or target not in g:
        return {"path": [], "length": -1, "reason": "node not found"}
    di = nx.DiGraph(g)
    try:
        path = nx.shortest_path(di, source=source, target=target)
        return {"path": path, "length": len(path) - 1, "directed": True}
    except nx.NetworkXNoPath:
        pass
    try:
        path = nx.shortest_path(di.to_undirected(), source=source, target=target)
        return {"path": path, "length": len(path) - 1, "directed": False, "note": "no directed path; undirected fallback shown"}
    except nx.NetworkXNoPath:
        return {"path": [], "length": -1, "reason": "no path"}


def centrality(metric: str = "degree", limit: int = 25) -> list[dict]:
    g = build_graph()
    di = nx.DiGraph(g)
    if metric == "degree":
        scores = {n: d for n, d in g.degree()}
    elif metric == "in_degree":
        scores = dict(g.in_degree())
    elif metric == "out_degree":
        scores = dict(g.out_degree())
    elif metric == "pagerank":
        scores = nx.pagerank(di)
    elif metric == "betweenness":
        # Limit to sample for performance on larger graphs
        scores = nx.betweenness_centrality(di, k=min(50, len(di)) or None)
    elif metric == "eigenvector":
        try:
            scores = nx.eigenvector_centrality(di, max_iter=500)
        except nx.PowerIterationFailedConvergence:
            scores = {}
    else:
        return []
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit]
    out = []
    for nid, score in ranked:
        attrs = g.nodes.get(nid, {})
        out.append({
            "id": nid,
            "label": attrs.get("name") or attrs.get("sub_cap_name") or attrs.get("code") or nid,
            "kind": attrs.get("kind"),
            "score": float(score),
        })
    return out


def communities() -> list[dict]:
    g = build_graph()
    # Louvain is undirected; collapse multi-edges.
    ug = nx.Graph(nx.DiGraph(g).to_undirected())
    try:
        import community as community_louvain  # python-louvain

        partition = community_louvain.best_partition(ug, random_state=42)
    except Exception as e:
        log.warning("louvain failed: %s; falling back to connected components", e)
        partition = {n: i for i, comp in enumerate(nx.connected_components(ug)) for n in comp}
    by_comm: dict[int, list[str]] = {}
    for node, comm in partition.items():
        by_comm.setdefault(comm, []).append(node)
    out = []
    for comm_id, members in sorted(by_comm.items(), key=lambda x: -len(x[1])):
        out.append({"community_id": comm_id, "size": len(members), "members": members[:25]})
    return out


def impact_analysis(node_id: str, threshold: float = 0.5) -> dict:
    """If we remove this node, who loses ≥`threshold` of their connections?

    Considers neighbors in both directions: a successor S loses its incoming
    edges from `node_id`; a predecessor P loses its outgoing edges to
    `node_id`. We compute, per neighbor, the fraction of their TOTAL degree
    that disappears when `node_id` is removed.
    """
    g = build_graph()
    if node_id not in g:
        return {"affected": [], "reason": "node not found"}
    neighbors: set[str] = set(g.successors(node_id)) | set(g.predecessors(node_id))
    impacted = []
    for n in neighbors:
        in_total = g.in_degree(n)
        out_total = g.out_degree(n)
        in_lost = sum(1 for _ in g.in_edges(n) if _[0] == node_id)
        out_lost = sum(1 for _ in g.out_edges(n) if _[1] == node_id)
        in_frac = in_lost / in_total if in_total else 0
        out_frac = out_lost / out_total if out_total else 0
        worst = max(in_frac, out_frac)
        if worst >= threshold:
            attrs = g.nodes.get(n, {})
            impacted.append({
                "id": n,
                "label": attrs.get("name") or attrs.get("sub_cap_name") or n,
                "kind": attrs.get("kind"),
                "fraction_in_lost": in_frac,
                "fraction_out_lost": out_frac,
                "fraction_lost": worst,
            })
    impacted.sort(key=lambda x: -x["fraction_lost"])
    return {"target": node_id, "affected": impacted}


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _nid(kind: str, key: str) -> str:
    return f"{kind}:{key}"


def _safe(d: dict) -> dict:
    """Drop fields that conflict with NetworkX node attribute reserved names."""
    return {k: v for k, v in d.items() if k != "id"}


def _to_payload(sub: nx.MultiDiGraph) -> dict:
    nodes = []
    for n, attrs in sub.nodes(data=True):
        nodes.append({"data": {"id": n, "label": attrs.get("name") or attrs.get("sub_cap_name") or n, **{k: v for k, v in attrs.items() if k != "id"}}})
    edges: list[dict[str, Any]] = []
    for u, v, attrs in sub.edges(data=True):
        edges.append({"data": {"id": f"{u}->{v}::{attrs.get('kind')}", "source": u, "target": v, "kind": attrs.get("kind")}})
    return {"nodes": nodes, "edges": edges}


# ─── Sharded persistence (per QA_AUDIT.md fix #11) ──────────────────────────
#
# Firestore docs are limited to 1 MB. Persist the KG as N node-shards and
# M edge-shards where each shard is ≤ 200 nodes / 500 edges so we always
# stay well under the limit.

NODE_SHARD_SIZE = 200
EDGE_SHARD_SIZE = 500


def persist_snapshot(snapshot_id: str | None = None) -> dict:
    """Write the current graph to ``graph_snapshots`` as sharded docs.

    Returns shard metadata; round-trip with :func:`load_snapshot`.
    """
    g = build_graph(snapshot_id)
    sid = snapshot_id or _current_snapshot_id()
    repo = get_repository()
    nodes = [{"id": n, **dict(g.nodes[n])} for n in g.nodes()]
    edges = [
        {"source": u, "target": v, **dict(d)}
        for u, v, d in g.edges(data=True)
    ]
    node_shards = [nodes[i:i + NODE_SHARD_SIZE] for i in range(0, len(nodes), NODE_SHARD_SIZE)]
    edge_shards = [edges[i:i + EDGE_SHARD_SIZE] for i in range(0, len(edges), EDGE_SHARD_SIZE)]
    with repo.defer_persist():
        for i, shard in enumerate(node_shards):
            repo.upsert(
                "graph_snapshot_shards",
                f"{sid}-nodes-{i:04d}",
                {
                    "snapshot_id": sid,
                    "kind": "nodes",
                    "shard_index": i,
                    "_schema_version": "graph-shard-v1",
                    "rows": shard,
                },
            )
        for i, shard in enumerate(edge_shards):
            repo.upsert(
                "graph_snapshot_shards",
                f"{sid}-edges-{i:04d}",
                {
                    "snapshot_id": sid,
                    "kind": "edges",
                    "shard_index": i,
                    "_schema_version": "graph-shard-v1",
                    "rows": shard,
                },
            )
    return {
        "snapshot_id": sid,
        "node_shards": len(node_shards),
        "edge_shards": len(edge_shards),
        "nodes_total": len(nodes),
        "edges_total": len(edges),
    }


def load_snapshot(snapshot_id: str) -> nx.MultiDiGraph:
    """Re-hydrate a graph from sharded docs."""
    repo = get_repository()
    shards = [
        s for s in repo.list("graph_snapshot_shards")
        if s.get("snapshot_id") == snapshot_id
    ]
    g = nx.MultiDiGraph()
    for s in sorted(shards, key=lambda x: (x.get("kind"), x.get("shard_index", 0))):
        if s.get("kind") == "nodes":
            for n in s.get("rows", []):
                nid = n.get("id")
                attrs = {k: v for k, v in n.items() if k != "id"}
                g.add_node(nid, **attrs)
        elif s.get("kind") == "edges":
            for e in s.get("rows", []):
                src, dst = e.get("source"), e.get("target")
                attrs = {k: v for k, v in e.items() if k not in ("source", "target")}
                g.add_edge(src, dst, **attrs)
    return g
