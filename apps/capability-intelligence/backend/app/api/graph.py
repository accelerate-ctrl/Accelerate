"""Knowledge Graph — nodes, edges, queries, path, centrality, communities, impact."""
from fastapi import APIRouter, Depends, HTTPException, Query

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
