"""Audit-fix verification tests.

Per QA_AUDIT.md every P0 fix must have a measurable AC. This module
covers the structural fixes that aren't yet covered by per-feature tests:

    Fix #1  G1..G8 spec-parity gates             → test_g1..g8_*
    Fix #2  Embedded QA mixin                    → test_embedded_qa_*
    Fix #3  Reproducibility manifest             → test_manifest_*
    Fix #4  Schema-version registry              → test_schema_versions_*
    Fix #5  Leverage tiers + multi-sample +
            primary-source dedup + retraction    → test_loop_*
    Fix #6  Hierarchical bootstrap CI +
            dimensional validator                → test_bench_*
    Fix #7  Cluster service + cross-pillar       → test_cluster_*
    Fix #8  Graph 28 node types + sharded persist → test_graph_*
    Fix #11 Cost attribution                     → test_cost_attribution_*
    Fix #14 Source policy sidecar                → test_source_policy_*
    Fix #16 Entity resolver metrics              → test_entity_metrics_*
    Fix #18 Knowledge maturation                 → test_knowledge_*
"""

import pytest

from app.mixins.embedded_qa import (
    Check,
    EmbeddedQAResult,
    has_keys,
    non_empty_list,
    number_in_range,
    run_self_test,
)
from app.models.common import SCHEMA_VERSIONS, schema_version
from app.observability import emit_manifest
from app.services.benchmarks_service import (
    hierarchical_bootstrap_ci,
    validate_metric,
)
from app.services.consultant_loop import (
    LeverageTier,
    _dedup_by_primary,
    _resolve_contradiction,
)
from app.services.knowledge_maturation import (
    on_corroborating_source,
    on_source_retraction,
    recompute_label_for_edge,
)
from app.services.source_policy import (
    independence_class,
    is_disabled,
    policy_for,
    rate_limits,
)
from app.services.validation_gates_service import (
    gate_g1_novelty,
    gate_g2_source_quality,
    gate_g3_ers,
    gate_g4_independence,
    gate_g5_consistency,
    gate_g6_adversarial,
    gate_g7_drift,
    gate_g8_absence,
    run_gates,
)

# ─── Embedded QA ────────────────────────────────────────────────────────────


def test_embedded_qa_passes_when_predicates_pass():
    out = run_self_test(
        {"a": 1, "b": [1, 2, 3]},
        checks=[has_keys("a", "b"), non_empty_list("b", min_len=2)],
    )
    assert out.self_test_passed is True
    assert all(c.passed for c in out.self_test_log)


def test_embedded_qa_records_failures():
    out = run_self_test(
        {"a": None},
        checks=[has_keys("a", "b"), non_empty_list("b", min_len=1)],
    )
    assert out.self_test_passed is False
    assert any(not c.passed for c in out.self_test_log)


def test_embedded_qa_handles_predicate_exception():
    out = run_self_test({"x": 1}, checks=[("explodes", lambda p: p["missing"], "raised")])
    assert out.self_test_passed is False


def test_number_in_range_predicate():
    chk = number_in_range("score", 0, 100)
    assert run_self_test({"score": 50}, checks=[chk]).self_test_passed
    assert not run_self_test({"score": 150}, checks=[chk]).self_test_passed


# ─── Schema versions ────────────────────────────────────────────────────────


def test_schema_versions_registry_complete():
    """Every domain object the audit listed must be registered."""
    required = {
        "subcap", "reasoning_chain", "suggestion", "benchmark_observation",
        "benchmark_distribution", "lifecycle_score", "client_journey",
        "dma_packet", "strategic_digest", "digest_priority", "audit_report",
        "chat_conversation", "notification", "eval_run",
        "reproducibility_manifest", "capability_cluster", "delta_report",
    }
    assert required <= set(SCHEMA_VERSIONS.keys())


def test_schema_version_lookup_raises_on_unknown():
    with pytest.raises(KeyError):
        schema_version("does-not-exist")


def test_schema_version_returns_canonical_string():
    assert schema_version("dma_packet") == "dma-handoff-v1"


# ─── Manifest ───────────────────────────────────────────────────────────────


def test_emit_manifest_returns_required_fields(settings_for_tests):
    m = emit_manifest("run-test-1", operation_type="unit_test", rng_seed=42)
    assert m["_schema_version"] == "manifest-v1"
    assert m["run_id"] == "run-test-1"
    assert m["operation_type"] == "unit_test"
    assert m["rng_seed"] == 42
    assert m["model_versions"]
    assert m["config_hash"]
    assert m["timestamp"]


def test_emit_manifest_persists_to_repo(settings_for_tests):
    from app.services.repository import get_repository

    emit_manifest("run-persist-test", operation_type="x")
    rec = get_repository().get("reproducibility_manifests", "run-persist-test")
    assert rec is not None
    assert rec["run_id"] == "run-persist-test"


# ─── G1..G8 spec gates ─────────────────────────────────────────────────────


def test_g1_passes_on_novel_output():
    r = gate_g1_novelty({"claims": [{"text": "fresh"}]}, recent_outputs=[])
    assert r.verdict == "pass"


def test_g2_passes_on_t1_or_2t2():
    src_t1 = [{"id": "a", "tier": "T1"}]
    src_2t2 = [{"id": "a", "tier": "T2"}, {"id": "b", "tier": "T2"}]
    src_t5 = [{"id": "a", "tier": "T5"}]
    assert gate_g2_source_quality({}, src_t1).verdict == "pass"
    assert gate_g2_source_quality({}, src_2t2).verdict == "pass"
    assert gate_g2_source_quality({}, src_t5).verdict == "fail"


def test_g3_ers_components_in_range():
    r = gate_g3_ers(
        {"claims": [{"text": "x", "subcap_id": "P1C1.1.1"}]},
        [{"id": "a", "tier": "T1", "primary_source_id": "p1",
          "published_at": "2026-01-01T00:00:00+00:00"}],
    )
    assert 0 <= r.score <= 1
    assert "components" in r.details


def test_g4_passes_on_two_distinct_primaries():
    r = gate_g4_independence(
        {},
        [{"id": "a", "primary_source_id": "P"}, {"id": "b", "primary_source_id": "Q"}],
    )
    assert r.verdict == "pass"


def test_g4_fails_on_single_primary():
    r = gate_g4_independence(
        {},
        [{"id": "a", "primary_source_id": "P"}, {"id": "b", "primary_source_id": "P"}],
    )
    assert r.verdict == "fail"


def test_g5_passes_on_consistent():
    r = gate_g5_consistency({"claims": [{"text": "X is true"}, {"text": "Y is true"}]})
    assert r.verdict == "pass"


def test_g5_warns_on_contradiction():
    r = gate_g5_consistency({"claims": [
        {"text": "OCC issued guidance for retail banking"},
        {"text": "OCC has not issued guidance for retail banking"},
    ]})
    assert r.verdict == "warn"


def test_g6_marks_degraded_when_anthropic_down():
    r = gate_g6_adversarial({"verdict": "pass", "score": 0.9, "issues": []},
                            anthropic_degraded=True)
    assert r.verdict == "warn"
    assert r.details["degraded"] is True


def test_g7_warming_up_under_threshold():
    r = gate_g7_drift({"ers": 0.7}, history=[{"ers": 0.7}], min_history=50)
    assert r.verdict == "warn"
    assert r.details.get("warming_up") is True


def test_g8_passes_when_no_absence_claim():
    r = gate_g8_absence({"claims": [{"text": "X happened"}]}, sources=[])
    assert r.verdict == "pass"


def test_g8_warns_on_absence_without_search_trail():
    r = gate_g8_absence({"claims": [{"text": "no evidence found"}]}, sources=[], k=5)
    assert r.verdict == "warn"


def test_run_gates_returns_15_gate_rows():
    out = run_gates(
        {"claims": [{"text": "x", "sources": ["a"], "subcap_id": "P1C1.1.1"}]},
        sources=[{"id": "a", "tier": "T1", "primary_source_id": "p1",
                  "published_at": "2026-01-01T00:00:00+00:00"}],
    )
    names = {r.name for r in out.results}
    assert {f"g{i}_*" for i in (1,)} or True  # noqa: literal placeholder
    assert {"g1_novelty", "g2_source_quality", "g3_ers", "g4_independence",
            "g5_consistency", "g6_adversarial", "g7_drift", "g8_absence"} <= names
    assert {"aux_schema", "aux_citation", "aux_hallucination",
            "aux_freshness", "aux_bias", "aux_breaking_change",
            "aux_peer_coverage"} <= names


# ─── Loop helpers ───────────────────────────────────────────────────────────


def test_dedup_by_primary_collapses_circular_cite():
    dedup = _dedup_by_primary([
        {"id": "ffiec", "primary_source_id": "OCC-2024"},
        {"id": "occ-press", "primary_source_id": "OCC-2024"},
        {"id": "trade", "primary_source_id": "OCC-2024"},
    ])
    assert len(dedup) == 1


def test_dedup_by_primary_keeps_distinct():
    dedup = _dedup_by_primary([
        {"id": "fdic", "primary_source_id": "FDIC-2024"},
        {"id": "occ", "primary_source_id": "OCC-2024"},
    ])
    assert len(dedup) == 2


def test_resolve_contradiction_retraction_trumps_tier():
    a = {"id": "a", "tier": "T1", "text": "OCC issued guidance"}
    b = {"id": "b", "tier": "T2", "text": "OCC retracted prior guidance"}
    assert _resolve_contradiction(a, b)["id"] == "b"


def test_resolve_contradiction_tier_wins_when_no_retraction():
    a = {"id": "a", "tier": "T2", "text": "X is true",
         "published_at": "2026-04-01"}
    b = {"id": "b", "tier": "T1", "text": "X is false",
         "published_at": "2026-04-01"}
    assert _resolve_contradiction(a, b)["id"] == "b"


def test_resolve_contradiction_recency_wins_same_tier():
    a = {"id": "old", "tier": "T1", "text": "X",
         "published_at": "2024-01-01"}
    b = {"id": "new", "tier": "T1", "text": "Y",
         "published_at": "2026-01-01"}
    assert _resolve_contradiction(a, b)["id"] == "new"


def test_leverage_tier_enum_complete():
    assert {t.value for t in LeverageTier} == {"low", "medium", "high", "digest"}


# ─── Benchmarks: hierarchical bootstrap + dimensional validator ────────────


def test_hierarchical_bootstrap_collapses_correlated_obs():
    out = hierarchical_bootstrap_ci(
        [{"value": 10 + i, "primary_source_id": "P"} for i in range(6)],
        B=200,
    )
    assert out["effective_n"] == 1


def test_hierarchical_bootstrap_keeps_independent_obs():
    out = hierarchical_bootstrap_ci(
        [{"value": 10 + i, "primary_source_id": f"p{i}"} for i in range(6)],
        B=200,
    )
    assert out["effective_n"] == 6


def test_validate_metric_accepts_in_range():
    ok, _ = validate_metric("tech_spend_pct_revenue", 11.5)
    assert ok


def test_validate_metric_rejects_oor():
    ok, err = validate_metric("tech_spend_pct_revenue", 82.0)
    assert ok is False
    assert err and "outside" in err


def test_validate_metric_unknown_metric_passes_with_no_error():
    ok, _ = validate_metric("unknown_metric_id", 999)
    assert ok


# ─── Cluster + cross-pillar ─────────────────────────────────────────────────


def test_cluster_bootstrap_returns_clusters_when_p1_loaded(settings_for_tests):
    from app.services import catalogue_service, cluster_service
    catalogue_service.refresh_pillar("P1", by="test")
    clusters = cluster_service.bootstrap_clusters_from_pillar1(n_clusters=8)
    assert len(clusters) >= 1
    # Every cluster carries a 256-dim centroid + member list
    for c in clusters:
        assert len(c["centroid"]) == 256
        assert isinstance(c.get("member_subcap_ids"), list)


def test_cluster_assign_uses_existing_cluster(settings_for_tests):
    from app.services import catalogue_service, cluster_service
    catalogue_service.refresh_pillar("P1", by="test")
    cluster_service.bootstrap_clusters_from_pillar1(n_clusters=4)
    fake_cap = {"sub_cap_id": "P2C1.1.1", "sub_cap_name": "Digital Strategy",
                "description": "documented digital transformation",
                "l1_capability": "Strategy", "category_id": "P2C1"}
    cid, sim = cluster_service.assign_to_cluster(fake_cap, threshold=0.0)
    assert cid is not None
    assert 0 <= sim <= 1


# ─── Knowledge maturation ───────────────────────────────────────────────────


def test_recompute_label_demotes_when_source_removed(settings_for_tests):
    from app.services.repository import get_repository
    repo = get_repository()
    repo.upsert(
        "graph_edges", "edge-x",
        {
            "id": "edge-x", "claim_label": "FACT",
            "sources": [{"id": "s1", "tier": "T1"}, {"id": "s2", "tier": "T1"}],
        },
    )
    new_label = recompute_label_for_edge("edge-x", exclude_source="s1")
    assert new_label in ("HYPOTHESIS", "INFERENCE", "CEILING_ESTIMATE")


def test_on_source_retraction_demotes_affected_edges(settings_for_tests):
    from app.services.repository import get_repository
    repo = get_repository()
    repo.upsert(
        "graph_edges", "edge-y",
        {
            "id": "edge-y", "claim_label": "FACT",
            "sources": [{"id": "s1", "tier": "T1"}, {"id": "s2", "tier": "T1"}],
        },
    )
    out = on_source_retraction("s1")
    assert out["edges_affected"] == 1
    edge = repo.get("graph_edges", "edge-y")
    assert edge["claim_label"] != "FACT"


def test_on_corroborating_source_promotes(settings_for_tests):
    from app.services.repository import get_repository
    repo = get_repository()
    repo.upsert("graph_edges", "edge-z", {
        "id": "edge-z", "claim_label": "HYPOTHESIS",
        "sources": [{"id": "s1", "tier": "T2"}],
    })
    res = on_corroborating_source("edge-z", {"id": "s2", "tier": "T2"})
    assert res["from_label"] == "HYPOTHESIS"
    assert res["to_label"] == "INFERENCE"


# ─── Source policy ──────────────────────────────────────────────────────────


def test_source_policy_default():
    pol = policy_for("some-unconfigured-source")
    assert pol["tos_status"] == "accepted-risk"
    assert "max_requests_per_minute" in pol


def test_source_policy_disabled_for_linkedin():
    assert is_disabled("linkedin") is True


def test_source_policy_independence_class_overrides():
    assert independence_class("gartner_fs") == "analyst"
    assert independence_class("salesforce_news") == "self"


def test_source_policy_rate_limits_have_required_keys():
    rl = rate_limits("occ")
    assert "max_requests_per_minute" in rl
    assert "backoff_policy" in rl
    assert rl["max_requests_per_minute"] <= 10


# ─── Cost attribution ──────────────────────────────────────────────────────


def test_cost_tracker_attributed_query(settings_for_tests):
    from app.services.llm.cost_tracker import CostTracker
    from app.services.llm.router import ModelKind

    tracker = CostTracker()
    tracker.record(ModelKind.OPUS, 1000, 1000, 0.06,
                    operation_type="digest", subvertical="retail-banking")
    tracker.record(ModelKind.SONNET, 1000, 1000, 0.012,
                    operation_type="suggestion", subvertical="retail-banking")
    only_digest = tracker.attributed_spend(
        operation_type="digest", subvertical="retail-banking", days=1,
    )
    assert round(only_digest, 4) == 0.06


# ─── Entity resolver metrics ───────────────────────────────────────────────


def test_entity_resolver_metrics_evaluate(settings_for_tests):
    from app.services.entity_resolver_metrics import evaluate
    out = evaluate()
    assert "precision" in out
    assert "recall" in out
    # We don't assert thresholds here — those are post-fix-16 acceptance
    # criteria; this test asserts the metric harness loads + returns shape.
    assert out["n_positive"] > 0
    assert out["n_negative"] > 0


# ─── Graph: 28 spec node types + sharded persist ───────────────────────────


def test_graph_persist_and_load_roundtrip(settings_for_tests):
    from app.services import catalogue_service, graph_service
    catalogue_service.refresh_pillar("P1", by="test")
    out = graph_service.persist_snapshot()
    assert out["nodes_total"] > 0
    assert out["node_shards"] >= 1
    g_loaded = graph_service.load_snapshot(out["snapshot_id"])
    assert g_loaded.number_of_nodes() == out["nodes_total"]
    assert g_loaded.number_of_edges() == out["edges_total"]


def test_graph_includes_extended_node_kinds_when_collections_loaded(settings_for_tests):
    from app.services import catalogue_service, graph_service
    from app.services.repository import get_repository
    catalogue_service.refresh_pillar("P1", by="test")
    repo = get_repository()
    repo.upsert("vendor_profiles", "salesforce", {"vendor_id": "salesforce", "name": "Salesforce"})
    repo.upsert("benchmark_distributions", "dist-x",
                {"id": "dist-x", "metric_id": "tech_spend_pct_revenue", "cohort_id": "us_banks_gsib",
                 "verdict": "INDICATIVE"})
    repo.upsert("suggestions", "sug-x", {"id": "sug-x", "kind": "add_use_case",
                                         "target": "P1C1.1.1", "status": "pending"})
    repo.upsert("reasoning_chains", "chain-x",
                {"chain_id": "chain-x", "overall": "pass", "total_cost_usd": 0.0})
    repo.upsert("audit_reports", "audit-x", {"report_id": "audit-x", "summary": {}, "findings": []})
    graph_service.invalidate_cache()
    g = graph_service.build_graph()
    kinds = {d.get("kind") for _, d in g.nodes(data=True)}
    expected = {"Vendor", "Benchmark", "Suggestion", "ReasoningChain", "AuditFinding"}
    assert expected <= kinds
