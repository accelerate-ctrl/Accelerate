"""TRD §10 — SLO catalogue + alert rule tests."""

from __future__ import annotations

import pytest

from app.services.observability import slos


def test_registry_has_five_canonical_slos():
    ids = set(slos.SLO_REGISTRY.keys())
    assert ids == {
        "health",
        "catalogue_ingest",
        "chat_first_token",
        "graph_query",
        "digest_run",
    }


def test_list_slos_serialises_each_definition():
    rows = slos.list_slos()
    assert len(rows) == 5
    for r in rows:
        assert "slo_id" in r
        assert "target_ratio" in r
        assert "fast_window" in r
        assert "slow_window" in r
        assert r["severity"] in {"page", "ticket", "info"}


def test_list_alerts_emits_fast_plus_slow_per_slo():
    alerts = slos.list_alerts()
    by_id: dict[str, list] = {}
    for a in alerts:
        by_id.setdefault(a.slo_id, []).append(a.window)
    for windows in by_id.values():
        assert sorted(windows) == ["fast", "slow"]
    assert len(alerts) == 2 * len(slos.SLO_REGISTRY)


def test_fast_window_inherits_slo_severity():
    health_alerts = [a for a in slos.list_alerts() if a.slo_id == "health"]
    fast = next(a for a in health_alerts if a.window == "fast")
    slow = next(a for a in health_alerts if a.window == "slow")
    assert fast.severity == "page"
    assert slow.severity == "ticket"


def test_burn_rate_scales_with_window_budget_fraction():
    alerts = {a.name: a for a in slos.list_alerts()}
    fast = alerts["health.fast_burn"]
    slow = alerts["health.slow_burn"]
    # Health SLO target is 0.9995 → budget is 0.0005. Fast lookback 1h
    # burns 0.02 of the monthly budget, slow 24h burns 0.05 — fast burn
    # rate should be higher.
    assert fast.threshold_burn_rate > slow.threshold_burn_rate


def test_render_alert_policies_is_json_serialisable():
    import json
    payload = slos.render_alert_policies()
    json.dumps(payload)  # no exception → all fields are primitive


def test_dump_registry_json_roundtrip():
    import json
    payload = json.loads(slos.dump_registry_json())
    assert {"slos", "alert_policies"} == set(payload.keys())
    assert len(payload["slos"]) == 5


def test_evaluate_in_compliance():
    ev = slos.evaluate_slo("health", good=9999, total=10000, latency_p95_ms=120)
    assert ev.in_compliance
    assert ev.latency_breach is False
    assert ev.actual_ratio >= 0.999


def test_evaluate_out_of_compliance():
    ev = slos.evaluate_slo("health", good=900, total=1000)
    assert ev.in_compliance is False
    assert ev.error_budget_used == 1.0  # capped


def test_evaluate_flags_latency_breach():
    ev = slos.evaluate_slo("health", good=9999, total=10000, latency_p95_ms=500)
    assert ev.latency_breach is True
    assert any("p95" in note for note in ev.notes)


def test_evaluate_chat_latency_threshold():
    ev = slos.evaluate_slo(
        "chat_first_token", good=1000, total=1000, latency_p95_ms=2500
    )
    assert ev.latency_breach is True
    assert ev.in_compliance is True  # availability still 100%


def test_evaluate_rejects_unknown_slo():
    with pytest.raises(KeyError):
        slos.evaluate_slo("nonexistent", good=1, total=1)


def test_evaluate_rejects_invalid_sample():
    with pytest.raises(ValueError):
        slos.evaluate_slo("health", good=10, total=5)


def test_evaluate_handles_zero_total():
    ev = slos.evaluate_slo("health", good=0, total=0)
    assert ev.in_compliance
    assert ev.actual_ratio == 1.0


def test_target_ratios_are_strict():
    # Sanity floor — none of our SLO targets should slip below 99%.
    for slo in slos.SLO_REGISTRY.values():
        assert slo.target_ratio >= 0.99


def test_alert_documentation_inherits_slo_description():
    for alert in slos.list_alerts():
        slo = slos.SLO_REGISTRY[alert.slo_id]
        assert alert.documentation == slo.description
        assert alert.target_ratio == slo.target_ratio
