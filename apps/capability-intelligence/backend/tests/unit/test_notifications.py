"""Notification feed builder."""

from datetime import datetime, timedelta, timezone

import pytest

from app.services import notifications_service
from app.services.repository import get_repository


def test_refresh_with_empty_repo(settings_for_tests):
    summary = notifications_service.refresh()
    assert summary.new_count == 0
    assert summary.total_count == 0
    assert notifications_service.list_notifications() == []


def test_refresh_pulls_audit_critical(settings_for_tests):
    repo = get_repository()
    repo.upsert(
        "audit_reports",
        "audit-fake-1",
        {
            "report_id": "audit-fake-1",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "findings": [
                {
                    "kind": "GATE_FAIL",
                    "severity": "critical",
                    "title": "Chain failed gates",
                    "detail": "Overall verdict=fail",
                    "ref_collection": "reasoning_chains",
                    "ref_id": "chain-x",
                },
            ],
            "summary": {"critical": 1, "warn": 0, "info": 0},
        },
    )
    summary = notifications_service.refresh()
    assert summary.new_count == 1
    items = notifications_service.list_notifications(severity="critical")
    assert items
    assert items[0]["kind"] == "AUDIT_CRITICAL"


def test_refresh_pulls_recent_lifecycle_transition(settings_for_tests):
    repo = get_repository()
    now = datetime.now(timezone.utc).isoformat()
    repo.upsert(
        "lifecycle_transitions",
        "trans-1",
        {
            "id": "trans-1",
            "sub_cap_id": "P1C1.1.1",
            "from_state": "EMERGING",
            "to_state": "RISING",
            "score": 78.5,
            "transitioned_at": now,
        },
    )
    notifications_service.refresh()
    items = notifications_service.list_notifications()
    transitions = [n for n in items if n["kind"] == "LIFECYCLE_TRANSITION"]
    assert transitions
    assert transitions[0]["severity"] == "info"


def test_refresh_skips_old_lifecycle_transition(settings_for_tests):
    repo = get_repository()
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    repo.upsert(
        "lifecycle_transitions",
        "trans-old",
        {
            "id": "trans-old",
            "sub_cap_id": "P1C1.1.1",
            "from_state": "STABLE",
            "to_state": "FADING",
            "score": 22,
            "transitioned_at": old,
        },
    )
    notifications_service.refresh()
    items = notifications_service.list_notifications()
    assert all(n["kind"] != "LIFECYCLE_TRANSITION" for n in items)


def test_refresh_pulls_pending_suggestions(settings_for_tests):
    repo = get_repository()
    repo.upsert(
        "suggestions",
        "sug-x",
        {
            "id": "sug-x",
            "kind": "add_use_case",
            "target": "P1C1.1.1",
            "title": "Pilot GenAI co-author",
            "status": "pending",
            "gate_overall": "warn",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    notifications_service.refresh()
    items = notifications_service.list_notifications()
    pending = [n for n in items if n["kind"] == "SUGGESTION_PENDING"]
    assert pending


def test_mark_read_persists(settings_for_tests):
    repo = get_repository()
    repo.upsert(
        "audit_reports",
        "audit-x",
        {
            "report_id": "audit-x",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "findings": [{
                "kind": "GATE_FAIL",
                "severity": "critical",
                "title": "x",
                "detail": "y",
                "ref_collection": "reasoning_chains",
                "ref_id": "chain-x",
            }],
            "summary": {"critical": 1, "warn": 0, "info": 0},
        },
    )
    notifications_service.refresh()
    items = notifications_service.list_notifications()
    nid = items[0]["id"]
    rec = notifications_service.mark_read(nid)
    assert rec["read"] is True
    refetched = notifications_service.list_notifications(unread_only=True)
    assert all(n["id"] != nid for n in refetched)


def test_mark_all_read(settings_for_tests):
    repo = get_repository()
    repo.upsert(
        "lifecycle_transitions",
        "trans-1",
        {
            "id": "trans-1",
            "sub_cap_id": "P1C1.1.1",
            "from_state": "EMERGING",
            "to_state": "RISING",
            "transitioned_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    notifications_service.refresh()
    n = notifications_service.mark_all_read()
    assert n >= 1
    assert notifications_service.list_notifications(unread_only=True) == []


def test_stats_rollup(settings_for_tests):
    repo = get_repository()
    repo.upsert(
        "audit_reports",
        "audit-x",
        {
            "report_id": "audit-x",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "findings": [{
                "kind": "GATE_FAIL",
                "severity": "critical",
                "title": "x",
                "detail": "y",
                "ref_collection": "reasoning_chains",
                "ref_id": "chain-x",
            }],
            "summary": {"critical": 1, "warn": 0, "info": 0},
        },
    )
    notifications_service.refresh()
    s = notifications_service.stats()
    assert s["total"] >= 1
    assert s["critical"] >= 1
    assert s["unread"] >= 1
