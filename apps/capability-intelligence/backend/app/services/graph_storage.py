"""Sharded Firestore persistence for the knowledge graph (F05).

Background — QA_AUDIT F05: the existing :mod:`graph_service` keeps the
whole KG in an in-process NetworkX MultiDiGraph. At v7.0 production
scale (~14k nodes + ~60k edges across 4 pillars + KG Layer B
proposals) a single Firestore document would exceed the 1 MB limit
and a single process would lose the graph on restart.

This module persists the graph in two sharded collections:

- ``graph_nodes/shard_{n}`` — each shard document holds an array of
  KGNode maps (target ≤200 nodes per shard, ≤1 MB per document).
- ``graph_edges/shard_{n}`` — same pattern for edges.

Shard assignment is deterministic via ``hash(node_id) mod N_SHARDS``.
``N_SHARDS`` starts at 50 (covers ~10k nodes comfortably) and the
``ensure_capacity`` helper doubles it when the average shard size
exceeds 150 — keeps Firestore reads bounded as the graph grows.

The :class:`GraphStorage` API is intentionally thin: write the graph
in a single transactional pass (clear-then-write); read it back via a
shard-by-shard scan that rebuilds the NetworkX object for in-process
algorithms. Production deploys can later replace the in-process
NetworkX with a graph database without touching call sites.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

import networkx as nx

from app.models.common import schema_version

from .repository import get_repository

logger = logging.getLogger(__name__)

NODE_SHARD_COLLECTION = "graph_nodes"
EDGE_SHARD_COLLECTION = "graph_edges"
SHARD_STATE_DOC = "graph_shards/state"

DEFAULT_N_SHARDS = 50
MAX_NODES_PER_SHARD = 200
RESHARD_THRESHOLD = 150


@dataclass
class KGNode:
    node_id: str
    kind: str
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass
class KGEdge:
    src: str
    dst: str
    key: str
    kind: str
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass
class StorageSnapshot:
    snapshot_id: str
    n_shards: int
    node_count: int
    edge_count: int
    written_at: str
    avg_nodes_per_shard: float
    schema_version_: str = "graph-shard-v1"

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["_schema_version"] = out.pop("schema_version_")
        return out


# ─── Sharding helpers ──────────────────────────────────────────────────────


def _shard_for(node_id: str, n_shards: int) -> int:
    """Stable deterministic shard assignment.

    sha1 is overkill but it gives perfect distribution across N_SHARDS
    even for highly-correlated node ids (e.g. ``Subcap::P1C1.1.1``,
    ``Subcap::P1C1.1.2``, …). Mod-N is acceptable because we never
    delete shards — re-sharding writes a brand-new snapshot.
    """
    h = hashlib.sha1(node_id.encode("utf-8")).hexdigest()
    return int(h, 16) % n_shards


def _current_n_shards() -> int:
    """Read the shard count from the persisted state doc, falling back
    to the default. The state doc is updated on each save_snapshot()
    call so subsequent reads see the right shard count.
    """
    repo = get_repository()
    state = repo.get("graph_shards", "state")
    if state and isinstance(state.get("n_shards"), int):
        return state["n_shards"]
    return DEFAULT_N_SHARDS


def _ensure_capacity(n_nodes: int, current_n_shards: int) -> int:
    """Decide how many shards a new snapshot should use.

    If the average shard size would exceed RESHARD_THRESHOLD, double
    the shard count. Caps at 4096 so a misconfigured catalogue can't
    explode the shard count.
    """
    n = current_n_shards
    while n_nodes / max(1, n) > RESHARD_THRESHOLD and n < 4096:
        n *= 2
    return n


# ─── Public API ────────────────────────────────────────────────────────────


def save_snapshot(g: nx.MultiDiGraph, *, snapshot_id: str | None = None) -> StorageSnapshot:
    """Persist the entire graph as a shard-grouped snapshot.

    The write happens inside a single :meth:`Repository.defer_persist`
    block so a graph with thousands of nodes doesn't generate
    thousands of disk flushes.
    """
    started = datetime.now(timezone.utc)
    snapshot_id = snapshot_id or f"kg-{int(started.timestamp())}"
    repo = get_repository()

    n_nodes = g.number_of_nodes()
    n_edges = g.number_of_edges()
    n_shards = _ensure_capacity(n_nodes, _current_n_shards())

    # Bucket nodes by shard first. Each shard is a single Firestore doc.
    node_buckets: dict[int, list[dict]] = {i: [] for i in range(n_shards)}
    edge_buckets: dict[int, list[dict]] = {i: [] for i in range(n_shards)}

    for nid, attrs in g.nodes(data=True):
        idx = _shard_for(nid, n_shards)
        node_buckets[idx].append({
            "node_id": nid,
            "kind": attrs.get("kind"),
            "attrs": {k: v for k, v in attrs.items() if k != "kind"},
        })

    for u, v, attrs in g.edges(data=True, keys=False):
        # Edges follow their source-node shard so neighbourhood lookups
        # need only a single shard read.
        idx = _shard_for(u, n_shards)
        edge_buckets[idx].append({
            "src": u,
            "dst": v,
            "kind": attrs.get("kind"),
            "key": attrs.get("key", f"{attrs.get('kind', 'EDGE')}::{v}"),
            "attrs": {k: v_ for k, v_ in attrs.items() if k not in ("kind", "key")},
        })

    with repo.defer_persist():
        # Clear prior shards before re-writing so a smaller graph
        # doesn't leave dangling shards from the previous snapshot.
        _clear_shard_collection(repo, NODE_SHARD_COLLECTION)
        _clear_shard_collection(repo, EDGE_SHARD_COLLECTION)

        for idx in range(n_shards):
            nodes = node_buckets.get(idx) or []
            edges = edge_buckets.get(idx) or []
            if not nodes and not edges:
                continue
            shard_doc_id = f"shard_{idx}"
            repo.upsert(NODE_SHARD_COLLECTION, shard_doc_id, {
                "shard_idx": idx,
                "snapshot_id": snapshot_id,
                "n_shards": n_shards,
                "nodes": nodes,
                "_schema_version": schema_version("graph_snapshot_shard"),
            })
            repo.upsert(EDGE_SHARD_COLLECTION, shard_doc_id, {
                "shard_idx": idx,
                "snapshot_id": snapshot_id,
                "n_shards": n_shards,
                "edges": edges,
                "_schema_version": schema_version("graph_snapshot_shard"),
            })

        # Update the shard-state pointer so subsequent reads see the
        # new shard count.
        repo.upsert("graph_shards", "state", {
            "snapshot_id": snapshot_id,
            "n_shards": n_shards,
            "node_count": n_nodes,
            "edge_count": n_edges,
            "written_at": started.isoformat(),
        })

    snap = StorageSnapshot(
        snapshot_id=snapshot_id,
        n_shards=n_shards,
        node_count=n_nodes,
        edge_count=n_edges,
        written_at=started.isoformat(),
        avg_nodes_per_shard=round(n_nodes / max(1, n_shards), 2),
    )
    logger.info(
        "kg snapshot saved: %s nodes=%d edges=%d shards=%d avg=%s",
        snapshot_id, n_nodes, n_edges, n_shards, snap.avg_nodes_per_shard,
    )
    return snap


def load_snapshot() -> nx.MultiDiGraph:
    """Rebuild a NetworkX graph by scanning every shard.

    Returns an empty graph when no snapshot exists. The shard scan is
    O(N_SHARDS); each shard is a single Firestore read at production
    scale, so loading the full v7.0 KG takes ~50 reads instead of
    14k+.
    """
    repo = get_repository()
    g = nx.MultiDiGraph()
    for shard in repo.list(NODE_SHARD_COLLECTION):
        for node in shard.get("nodes") or []:
            attrs = dict(node.get("attrs") or {})
            attrs["kind"] = node.get("kind")
            g.add_node(node["node_id"], **attrs)
    for shard in repo.list(EDGE_SHARD_COLLECTION):
        for edge in shard.get("edges") or []:
            attrs = dict(edge.get("attrs") or {})
            attrs["kind"] = edge.get("kind")
            g.add_edge(
                edge["src"], edge["dst"],
                key=edge.get("key", f"{edge.get('kind', 'EDGE')}::{edge['dst']}"),
                **attrs,
            )
    return g


def neighborhood(node_id: str, *, hops: int = 1) -> dict[str, Any]:
    """Read just the shards that contain ``node_id`` and its 1-hop
    neighbourhood. Cheaper than loading the full graph for the Subcap
    Deep Dive's KG mini-view.

    Returns ``{nodes: [...], edges: [...], shard_reads: int}`` so the
    operator dashboard can monitor shard-read cost per query.
    """
    repo = get_repository()
    n_shards = _current_n_shards()
    seen_nodes: dict[str, dict] = {}
    seen_edges: list[dict] = []
    shard_reads = 0

    # Frontier expansion: start with the target shard, then pull every
    # shard referenced by edges out of the current frontier.
    pending_shards = {_shard_for(node_id, n_shards)}
    visited_shards: set[int] = set()
    visited_nodes: set[str] = {node_id}

    for _hop in range(hops + 1):
        next_pending: set[int] = set()
        for shard_idx in list(pending_shards):
            if shard_idx in visited_shards:
                continue
            visited_shards.add(shard_idx)
            node_shard = repo.get(NODE_SHARD_COLLECTION, f"shard_{shard_idx}")
            edge_shard = repo.get(EDGE_SHARD_COLLECTION, f"shard_{shard_idx}")
            shard_reads += 2

            if node_shard:
                for nd in node_shard.get("nodes") or []:
                    if nd["node_id"] in visited_nodes:
                        seen_nodes[nd["node_id"]] = nd

            if edge_shard:
                for ed in edge_shard.get("edges") or []:
                    if ed["src"] in visited_nodes or ed["dst"] in visited_nodes:
                        seen_edges.append(ed)
                        for endpoint in (ed["src"], ed["dst"]):
                            if endpoint not in visited_nodes:
                                visited_nodes.add(endpoint)
                                next_pending.add(_shard_for(endpoint, n_shards))
        pending_shards = next_pending

    # Pick up any nodes we discovered via edges but whose shard we
    # haven't yet visited.
    for n_id in visited_nodes:
        if n_id in seen_nodes:
            continue
        idx = _shard_for(n_id, n_shards)
        node_shard = repo.get(NODE_SHARD_COLLECTION, f"shard_{idx}")
        shard_reads += 1
        if not node_shard:
            continue
        for nd in node_shard.get("nodes") or []:
            if nd["node_id"] == n_id:
                seen_nodes[n_id] = nd
                break

    return {
        "nodes": list(seen_nodes.values()),
        "edges": seen_edges,
        "shard_reads": shard_reads,
    }


def state() -> dict[str, Any] | None:
    """Return the current snapshot state pointer (or ``None`` if no
    snapshot has been written yet)."""
    return get_repository().get("graph_shards", "state")


def _clear_shard_collection(repo, collection: str) -> None:
    for row in list(repo.list(collection)):
        doc_id = row.get("shard_idx")
        if doc_id is None:
            continue
        repo.delete(collection, f"shard_{doc_id}")


__all__ = [
    "DEFAULT_N_SHARDS",
    "EDGE_SHARD_COLLECTION",
    "KGEdge",
    "KGNode",
    "MAX_NODES_PER_SHARD",
    "NODE_SHARD_COLLECTION",
    "StorageSnapshot",
    "load_snapshot",
    "neighborhood",
    "save_snapshot",
    "state",
]
