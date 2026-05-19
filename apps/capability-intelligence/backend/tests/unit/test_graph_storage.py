"""Sharded KG persistence tests (QA_AUDIT F05 / Phase 3.2)."""

import networkx as nx
import pytest

from app.services import graph_storage
from app.services.graph_storage import (
    EDGE_SHARD_COLLECTION,
    NODE_SHARD_COLLECTION,
    _shard_for,
    load_snapshot,
    neighborhood,
    save_snapshot,
    state,
)
from app.services.repository import get_repository


def _make_graph(n_nodes: int, *, edges_per_node: int = 2) -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    for i in range(n_nodes):
        g.add_node(f"N{i}", kind="Subcap" if i % 2 == 0 else "Story",
                   label=f"Node {i}")
    # Each node points at the next two (modulo) to give a connected-ish
    # graph for neighbourhood walks.
    for i in range(n_nodes):
        for j in range(1, edges_per_node + 1):
            g.add_edge(
                f"N{i}", f"N{(i + j) % n_nodes}",
                key=f"NEXT::{j}",
                kind="NEXT", weight=j,
            )
    return g


# ─── Shard assignment ──────────────────────────────────────────────────────


def test_shard_for_is_deterministic():
    assert _shard_for("Subcap::P1C1.1.1", 50) == _shard_for("Subcap::P1C1.1.1", 50)


def test_shard_for_distributes_across_buckets():
    """SHA-1 mod-N should spread similar ids across many shards."""
    shards = {_shard_for(f"Subcap::P1C1.1.{i}", 50) for i in range(500)}
    # Across 500 correlated ids and 50 shards, the distribution should
    # touch many — assert at least 30 distinct shards.
    assert len(shards) >= 30


# ─── Save / load round-trip ────────────────────────────────────────────────


def test_save_then_load_preserves_node_attrs(settings_for_tests):
    g = _make_graph(20)
    save_snapshot(g)
    loaded = load_snapshot()
    assert loaded.number_of_nodes() == 20
    # Round-trip an attribute
    assert loaded.nodes["N3"]["kind"] == "Story"
    assert loaded.nodes["N3"]["label"] == "Node 3"


def test_save_then_load_preserves_edge_attrs(settings_for_tests):
    g = _make_graph(10, edges_per_node=3)
    save_snapshot(g)
    loaded = load_snapshot()
    # Each node has 3 outgoing edges → 30 total.
    assert loaded.number_of_edges() == 30
    # Edge attrs survive the round-trip.
    out_edges = list(loaded.out_edges("N0", data=True))
    weights = sorted([d["weight"] for _, _, d in out_edges])
    assert weights == [1, 2, 3]


def test_save_writes_shard_state_doc(settings_for_tests):
    g = _make_graph(30)
    snap = save_snapshot(g)
    s = state()
    assert s is not None
    assert s["n_shards"] == snap.n_shards
    assert s["node_count"] == 30


def test_resharding_kicks_in_at_threshold(settings_for_tests):
    """When the graph grows past RESHARD_THRESHOLD per shard, the shard
    count should double automatically."""
    # 50 default shards × 150 nodes/shard threshold = 7500
    g = _make_graph(8000, edges_per_node=1)
    snap = save_snapshot(g)
    assert snap.n_shards > 50
    # avg should now be below the threshold
    assert snap.avg_nodes_per_shard <= 150


def test_clear_drops_prior_shards(settings_for_tests):
    """Saving a smaller graph after a big one must not leave dangling
    shard documents around."""
    save_snapshot(_make_graph(1000))
    snap_small = save_snapshot(_make_graph(50))
    # Shards in the collection should match the new snapshot only.
    rows = get_repository().list(NODE_SHARD_COLLECTION)
    snapshot_ids = {r.get("snapshot_id") for r in rows}
    assert snapshot_ids == {snap_small.snapshot_id}


def test_empty_graph_round_trip(settings_for_tests):
    g = nx.MultiDiGraph()
    save_snapshot(g)
    loaded = load_snapshot()
    assert loaded.number_of_nodes() == 0
    assert loaded.number_of_edges() == 0


# ─── Shard read cost ──────────────────────────────────────────────────────


def test_neighborhood_reads_far_fewer_shards_than_total(settings_for_tests):
    """The neighbourhood helper must bound the read cost — full-graph
    load is O(N_SHARDS) but a 1-hop neighbourhood should touch only a
    small fraction of shards.
    """
    g = _make_graph(5000, edges_per_node=2)
    snap = save_snapshot(g)
    out = neighborhood("N42", hops=1)
    assert out["nodes"]  # at least the target node
    # 1-hop neighbourhood has the target + ~2 out-neighbours; even with
    # frontier expansion the shard reads should be at most a few dozen
    # — definitely less than the full shard count (50+).
    assert out["shard_reads"] < snap.n_shards


def test_neighborhood_returns_at_least_the_target_node(settings_for_tests):
    g = _make_graph(20)
    save_snapshot(g)
    out = neighborhood("N5", hops=0)
    node_ids = [n["node_id"] for n in out["nodes"]]
    assert "N5" in node_ids


def test_neighborhood_includes_one_hop_edges(settings_for_tests):
    g = _make_graph(10, edges_per_node=2)
    save_snapshot(g)
    out = neighborhood("N0", hops=1)
    # 2 outgoing edges from N0 must be in the result.
    n0_out = [e for e in out["edges"] if e["src"] == "N0"]
    assert len(n0_out) == 2


# ─── Integration with graph_service.build_graph ────────────────────────────


def test_can_persist_real_kg_snapshot(settings_for_tests):
    """The sharded persister handles the real graph_service output
    without choking on any specific node shape.
    """
    from app.services import graph_service
    graph_service.invalidate_cache()
    g = graph_service.build_graph()
    snap = save_snapshot(g)
    assert snap.node_count == g.number_of_nodes()
    assert snap.edge_count == g.number_of_edges()


def test_state_is_none_before_any_snapshot(settings_for_tests):
    assert state() is None
