"""Knowledge Graph — nodes, edges, queries, path, centrality, communities, impact."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from ..deps import auth_dep
from ..services import graph_service as gs

router = APIRouter()


@router.get("/_stub")
def stub(_=Depends(auth_dep)) -> dict:
    return {"module": "graph", "batch": 2, "status": "active"}


@router.get("/summary")
def summary(_=Depends(auth_dep)) -> dict:
    s = gs.summary()
    return {
        "snapshot_id": s.snapshot_id,
        "nodes_total": s.nodes_total,
        "edges_total": s.edges_total,
        "nodes_by_type": s.nodes_by_type,
        "edges_by_type": s.edges_by_type,
    }


@router.get("/elements")
def elements(
    kinds: str | None = Query(default=None, description="comma-separated node kinds"),
    max_nodes: int = 2000,
    _=Depends(auth_dep),
) -> dict:
    kind_list = [k.strip() for k in kinds.split(",")] if kinds else None
    return gs.export_for_render(node_kinds=kind_list, max_nodes=max_nodes)


@router.get("/neighborhood/{node_id}")
def neighborhood(node_id: str, hops: int = 1, _=Depends(auth_dep)) -> dict:
    if hops < 0 or hops > 5:
        raise HTTPException(400, "hops must be between 0 and 5")
    return gs.neighborhood(node_id, hops=hops)


@router.get("/path")
def path(source: str, target: str, _=Depends(auth_dep)) -> dict:
    return gs.shortest_path(source, target)


@router.get("/centrality")
def centrality(metric: str = "degree", limit: int = 25, _=Depends(auth_dep)) -> list[dict]:
    return gs.centrality(metric=metric, limit=limit)


@router.get("/communities")
def communities(_=Depends(auth_dep)) -> list[dict]:
    return gs.communities()


@router.get("/impact/{node_id}")
def impact(node_id: str, _=Depends(auth_dep)) -> dict:
    return gs.impact_analysis(node_id)


@router.get("/export.yaml", response_class=PlainTextResponse)
def export_yaml(
    max_nodes: int = 5000,
    _=Depends(auth_dep),
) -> PlainTextResponse:
    """Download the current snapshot as a YAML document.

    Includes every node with its kind + label + the edge list with source,
    target, and relation. Suitable for offline analysis or git-versioning.
    """
    import yaml as _yaml
    payload = gs.export_for_render(max_nodes=max_nodes)

    # Each item is `{data: {id, label, kind, ...}}` (Cytoscape envelope).
    def _unwrap(item: dict) -> dict:
        return item.get("data", item) if isinstance(item, dict) else {}

    nodes_out = []
    for n in payload.get("nodes", []):
        d = _unwrap(n)
        if not d.get("id"):
            continue
        nodes_out.append({"id": d["id"], "kind": d.get("kind"), "label": d.get("label")})

    edges_out = []
    for e in payload.get("edges", []):
        d = _unwrap(e)
        if not (d.get("source") and d.get("target")):
            continue
        edges_out.append({
            "source": d["source"],
            "target": d["target"],
            "relation": d.get("relation") or d.get("kind") or d.get("label"),
        })

    doc = {
        "snapshot_id": payload.get("snapshot_id"),
        "truncated": payload.get("truncated"),
        "nodes": nodes_out,
        "edges": edges_out,
    }
    text = _yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
    return PlainTextResponse(
        text,
        media_type="application/x-yaml",
        headers={"Content-Disposition": "attachment; filename=knowledge-graph.yaml"},
    )


@router.get("/insights")
def insights(_=Depends(auth_dep)) -> dict:
    """Surface structural anomalies in the graph that hint at gaps:

      * `orphaned_subcaps`   — Subcap nodes with no L1_Capability edge
      * `dense_communities`  — Top Louvain communities by node count
      * `bridge_nodes`       — Highest-betweenness nodes (info bottlenecks)
      * `duplicate_clusters` — Subcaps with near-identical names per pillar
                               (rapidfuzz ≥ 90% similarity)
    """
    return gs.graph_insights() if hasattr(gs, "graph_insights") else _fallback_insights(gs)


def _fallback_insights(gs_mod) -> dict:
    """Inline implementation if graph_service hasn't yet exposed
    graph_insights — keeps the endpoint useful while the service grows."""
    from rapidfuzz import fuzz
    payload = gs_mod.export_for_render(max_nodes=10_000)
    raw_nodes = payload.get("nodes", [])
    raw_edges = payload.get("edges", [])

    def _u(x: dict) -> dict:
        return x.get("data", x) if isinstance(x, dict) else {}

    nodes = [_u(n) for n in raw_nodes if _u(n).get("id")]
    edges = [_u(e) for e in raw_edges if _u(e).get("source") and _u(e).get("target")]

    by_kind: dict[str, list[dict]] = {}
    for n in nodes:
        by_kind.setdefault(n.get("kind") or "?", []).append(n)

    sub_ids = {n["id"] for n in by_kind.get("Subcap", [])}
    targeted = {e["target"] for e in edges if (e.get("relation") or e.get("kind")) in
                ("PART_OF", "REALIZES", "MAPS_TO", "BELONGS_TO")}
    orphans = sorted(sub_ids - targeted)[:25]

    dupes: list[dict] = []
    sub_pairs = by_kind.get("Subcap", [])
    seen: set = set()
    for i in range(len(sub_pairs)):
        for j in range(i + 1, min(i + 80, len(sub_pairs))):
            a, b = sub_pairs[i], sub_pairs[j]
            if a["id"] == b["id"]:
                continue
            la = (a.get("label") or "").lower()
            lb = (b.get("label") or "").lower()
            if not la or not lb:
                continue
            score = fuzz.token_set_ratio(la, lb)
            if score >= 90:
                key = tuple(sorted([a["id"], b["id"]]))
                if key in seen:
                    continue
                seen.add(key)
                dupes.append({"a": a["id"], "b": b["id"],
                              "a_label": a.get("label"), "b_label": b.get("label"),
                              "similarity": score})
            if len(dupes) >= 40:
                break
        if len(dupes) >= 40:
            break

    centrality_top = gs_mod.centrality(metric="betweenness", limit=10)
    communities_list = gs_mod.communities()[:8]

    return {
        "orphaned_subcaps": orphans,
        "duplicate_clusters": sorted(dupes, key=lambda d: -d["similarity"]),
        "bridge_nodes": centrality_top,
        "dense_communities": communities_list,
        "totals": {
            "nodes": len(nodes),
            "edges": len(edges),
            "by_kind": {k: len(v) for k, v in by_kind.items()},
        },
    }
