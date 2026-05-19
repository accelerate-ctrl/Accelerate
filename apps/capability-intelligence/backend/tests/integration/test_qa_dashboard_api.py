"""Phase 5 — QA & Audit Dashboard API tests (IMP-8/9/13)."""

from __future__ import annotations

import pytest

from app.services import retrieval_telemetry, source_health_digest, user_budget


def _auth_headers(email: str = "alice@zennify.com") -> dict[str, str]:
    return {"Authorization": f"Bearer dev-{email}"}


def test_retrieval_summary_default_window(client):
    retrieval_telemetry.record(
        query="P1C1.1.1 strategy",
        operation="chat",
        hits=[
            {
                "doc_id": "subcap:P1C1.1.1",
                "signal": "structured",
                "kind": "subcap",
                "score": 0.92,
                "fusion_score": 0.88,
                "metadata": {"sub_cap_id": "P1C1.1.1"},
            }
        ],
        user_email="alice@zennify.com",
    )
    r = client.get("/api/qa/retrieval/summary", headers=_auth_headers())
    assert r.status_code == 200
    body = r.json()
    assert "hits_by_signal" in body
    assert body["hits_by_signal"].get("structured", 0) >= 1


def test_retrieval_recent_filters_by_operation(client):
    retrieval_telemetry.record(query="x", operation="chat", hits=[], user_email="a@z")
    retrieval_telemetry.record(query="y", operation="digest", hits=[], user_email="a@z")
    r = client.get(
        "/api/qa/retrieval/recent?operation=chat", headers=_auth_headers()
    )
    assert r.status_code == 200
    rows = r.json()
    assert all(row["operation"] == "chat" for row in rows)


def test_my_budget_starts_clean(client):
    r = client.get("/api/qa/budgets/me", headers=_auth_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["spend_usd"] == 0.0
    assert body["should_downgrade"] is False


def test_my_budget_reflects_spend(client):
    user_budget.record_spend("alice@zennify.com", cost_usd=99.0)
    r = client.get("/api/qa/budgets/me", headers=_auth_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["spend_usd"] >= 99.0
    assert body["should_downgrade"] is True


def test_top_spenders_returns_list(client):
    user_budget.record_spend("alice@zennify.com", cost_usd=2.0)
    user_budget.record_spend("bob@zennify.com", cost_usd=4.0)
    r = client.get("/api/qa/budgets/top-spenders", headers=_auth_headers())
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 2
    # Newest spends first.
    assert rows[0]["spend_usd"] >= rows[-1]["spend_usd"]


def test_set_override_requires_admin(client):
    r = client.post(
        "/api/qa/budgets/overrides",
        json={"user_email": "alice@zennify.com", "budget_usd": 99.0},
        headers=_auth_headers(),
    )
    assert r.status_code == 403


def test_set_override_as_admin(client, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "admin@zennify.com")
    r = client.post(
        "/api/qa/budgets/overrides",
        json={"user_email": "alice@zennify.com", "budget_usd": 50.0, "reason": "VIP"},
        headers=_auth_headers("admin@zennify.com"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["user_email"] == "alice@zennify.com"
    assert body["daily_budget_usd"] == 50.0


def test_clear_override_as_admin(client, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "admin@zennify.com")
    user_budget.set_user_budget_override(
        "alice@zennify.com", daily_budget_usd=50.0, set_by="admin@zennify.com"
    )
    r = client.delete(
        "/api/qa/budgets/overrides/alice@zennify.com",
        headers=_auth_headers("admin@zennify.com"),
    )
    assert r.status_code == 200
    assert r.json()["cleared"] is True


def test_set_override_rejects_negative_budget(client, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "admin@zennify.com")
    r = client.post(
        "/api/qa/budgets/overrides",
        json={"user_email": "alice@zennify.com", "budget_usd": -5.0},
        headers=_auth_headers("admin@zennify.com"),
    )
    assert r.status_code == 400


def test_budgets_audit(client, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "admin@zennify.com")
    user_budget.set_user_budget_override(
        "alice@zennify.com", daily_budget_usd=10.0, set_by="admin@zennify.com"
    )
    r = client.get("/api/qa/budgets/audit", headers=_auth_headers())
    assert r.status_code == 200
    rows = r.json()
    assert any(r.get("user_email") == "alice@zennify.com" for r in rows)


def test_source_health_latest_empty(client):
    r = client.get("/api/qa/source-health/latest", headers=_auth_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["n_sources_seen"] == 0


def test_source_health_latest_with_events(client):
    for _ in range(4):
        source_health_digest.record_event("occ", "failure")
    r = client.get("/api/qa/source-health/latest", headers=_auth_headers())
    assert r.status_code == 200
    body = r.json()
    flagged = [row for row in body["rows"] if "high_failure_rate" in row["flags"]]
    assert flagged


def test_source_health_digests_list(client):
    source_health_digest.send_digest()
    r = client.get("/api/qa/source-health/digests", headers=_auth_headers())
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_source_health_run_now_requires_admin(client):
    r = client.post("/api/qa/source-health/run-now", headers=_auth_headers())
    assert r.status_code == 403


def test_source_health_run_now_as_admin(client, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAILS", "admin@zennify.com")
    r = client.post(
        "/api/qa/source-health/run-now",
        headers=_auth_headers("admin@zennify.com"),
    )
    assert r.status_code == 200
    assert "digest_id" in r.json()


def test_list_slos_returns_five(client):
    r = client.get("/api/qa/slos", headers=_auth_headers())
    assert r.status_code == 200
    body = r.json()
    assert len(body["slos"]) == 5
    assert len(body["alert_policies"]) == 10  # 2 per SLO


def test_eval_baselines_empty_by_default(client):
    r = client.get("/api/qa/eval/baselines", headers=_auth_headers())
    assert r.status_code == 200
    assert isinstance(r.json(), list)
