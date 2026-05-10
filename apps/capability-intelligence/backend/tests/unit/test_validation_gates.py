"""Per-gate unit tests + run_gates orchestrator."""

from datetime import datetime, timedelta, timezone

from app.services.validation_gates_service import (
    gate_bias,
    gate_breaking_change,
    gate_citation,
    gate_freshness,
    gate_hallucination,
    gate_novelty,
    gate_peer_coverage,
    gate_schema,
    run_gates,
)


def _src(sid, text="text body about banking and digital strategy", **kw):
    return {"id": sid, "text": text, "title": "src " + sid, **kw}


def test_schema_gate_passes_when_keys_present():
    r = gate_schema({"claims": []}, expected_keys=["claims"])
    assert r.verdict == "pass"


def test_schema_gate_fails_on_missing_keys():
    r = gate_schema({}, expected_keys=["claims"])
    assert r.verdict == "fail"


def test_citation_gate_fails_on_missing_citations():
    out = {"claims": [{"text": "x", "sources": []}]}
    r = gate_citation(out, [])
    assert r.verdict == "fail"


def test_citation_gate_warns_on_unresolved_id():
    out = {"claims": [{"text": "x", "sources": ["nonexistent"]}]}
    r = gate_citation(out, [_src("real-1")])
    assert r.verdict in ("warn", "fail")


def test_citation_gate_passes_when_all_resolve():
    out = {"claims": [{"text": "banking strategy", "sources": ["s1"]}]}
    r = gate_citation(out, [_src("s1")])
    assert r.verdict == "pass"


def test_hallucination_gate_passes_when_overlap_high():
    src = _src("s1", text="digital strategy document banking retail customer experience")
    out = {"claims": [{"text": "digital strategy document banking retail", "sources": ["s1"]}]}
    r = gate_hallucination(out, [src])
    assert r.verdict == "pass"


def test_hallucination_gate_fails_when_no_overlap():
    src = _src("s1", text="completely unrelated topic about gardening tomatoes")
    out = {"claims": [{"text": "blockchain crypto trading", "sources": ["s1"]}]}
    r = gate_hallucination(out, [src])
    assert r.verdict in ("warn", "fail")


def test_freshness_gate_fails_on_stale_majority():
    old = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
    sources = [_src(f"s{i}", published_at=old) for i in range(3)]
    r = gate_freshness(sources, max_age_days=365)
    assert r.verdict in ("warn", "fail")


def test_novelty_gate_warns_on_duplicate():
    out = {"claims": [{"text": "x"}]}
    r = gate_novelty(out, [out, out])
    assert r.verdict == "warn"


def test_bias_gate_warns_when_one_source_dominates():
    out = {"claims": [{"text": "a", "sources": ["s1"]}, {"text": "b", "sources": ["s1"]}, {"text": "c", "sources": ["s1"]}, {"text": "d", "sources": ["s2"]}]}
    r = gate_bias(out, [_src("s1"), _src("s2")])
    assert r.verdict == "warn"


def test_breaking_change_gate_warns_on_high_impact():
    suggestions = [{"kind": "delete_subcap", "target": "P1C1.1.1", "title": "x", "rationale": "y"}]
    r = gate_breaking_change(suggestions)
    assert r.verdict == "warn"


def test_peer_coverage_warns_when_no_benchmark():
    out = {"claims": [{"text": "Wells Fargo bank rolls out something"}]}
    r = gate_peer_coverage(out, [_src("s1")])
    assert r.verdict == "warn"


def test_peer_coverage_passes_when_benchmark_present():
    out = {"claims": [{"text": "Wells Fargo bank rolls out something"}]}
    r = gate_peer_coverage(out, [_src("s1", kind="benchmark")])
    assert r.verdict == "pass"


def test_run_gates_aggregates_overall_score():
    out = {"claims": [{"text": "digital banking strategy retail document", "sources": ["s1"]}]}
    sources = [_src("s1", text="digital banking strategy retail document customer", published_at=datetime.now(timezone.utc).isoformat(), kind="benchmark")]
    run = run_gates(out, sources, suggestions=[], recent_outputs=[])
    assert run.overall in ("pass", "warn")
    assert 0.0 <= run.score <= 1.0
    assert len(run.results) == 8  # all 8 gates ran
