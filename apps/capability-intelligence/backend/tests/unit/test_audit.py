"""Deep audit sweeps + report shape."""

from datetime import datetime, timedelta, timezone

import pytest

from app.services import audit_service
from app.services.audit_service import (
    SEVERITY_CRITICAL,
    SEVERITY_INFO,
    SEVERITY_WARN,
    _parse_iso,
)
from app.services.repository import get_repository


def test_parse_iso_coerces_naive_to_utc():
    dt = _parse_iso("2026-04-01T00:00:00")
    assert dt is not None
    assert dt.tzinfo is timezone.utc


def test_run_audit_with_empty_repo_returns_zero_findings(settings_for_tests):
    report = audit_service.run_audit()
    assert report.findings == []
    assert sum(report.summary.values()) == 0
    assert report.report_id.startswith("audit-")


def test_run_audit_picks_up_failed_chain(settings_for_tests):
    repo = get_repository()
    repo.upsert(
        "reasoning_chains",
        "chain-fail-1",
        {
            "chain_id": "chain-fail-1",
            "started_at": "2026-04-01T00:00:00+00:00",
            "overall": "fail",
            "gates": {"score": 0.2, "results": []},
        },
    )
    report = audit_service.run_audit()
    kinds = {f["kind"] for f in report.findings}
    assert "GATE_FAIL" in kinds
    assert report.summary[SEVERITY_CRITICAL] >= 1


def test_run_audit_picks_up_stale_suggestion(settings_for_tests):
    repo = get_repository()
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    repo.upsert(
        "suggestions",
        "sug-old",
        {
            "id": "sug-old",
            "status": "pending",
            "kind": "add_use_case",
            "target": "P1C1.1.1",
            "created_at": old,
        },
    )
    report = audit_service.run_audit()
    kinds = {f["kind"] for f in report.findings}
    assert "STALE_SUGGESTION" in kinds


def test_run_audit_skips_recent_suggestion(settings_for_tests):
    repo = get_repository()
    fresh = datetime.now(timezone.utc).isoformat()
    repo.upsert(
        "suggestions",
        "sug-fresh",
        {
            "id": "sug-fresh",
            "status": "pending",
            "kind": "add_use_case",
            "created_at": fresh,
        },
    )
    report = audit_service.run_audit()
    assert all(f["kind"] != "STALE_SUGGESTION" for f in report.findings)


def test_run_audit_dead_lifecycle_is_info(settings_for_tests):
    repo = get_repository()
    repo.upsert(
        "lifecycle_scores",
        "P9C9.9.9",
        {
            "sub_cap_id": "P9C9.9.9",
            "sub_cap_name": "Imaginary Subcap",
            "state": "DEAD",
            "score": 0,
        },
    )
    report = audit_service.run_audit()
    dead = [f for f in report.findings if f["kind"] == "DEAD_LIFECYCLE"]
    assert dead
    assert dead[0]["severity"] == SEVERITY_INFO


def test_list_reports_orders_newest_first(settings_for_tests):
    a = audit_service.run_audit()
    b = audit_service.run_audit()
    items = audit_service.list_reports()
    assert items[0]["report_id"] == b.report_id
    assert items[1]["report_id"] == a.report_id


def test_get_report_returns_persisted(settings_for_tests):
    r = audit_service.run_audit()
    fetched = audit_service.get_report(r.report_id)
    assert fetched is not None
    assert fetched["report_id"] == r.report_id
