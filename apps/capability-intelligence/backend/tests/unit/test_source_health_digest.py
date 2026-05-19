"""IMP-13 — source health digest tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services import source_health_digest as shd
from app.services.repository import get_repository


def _ts(delta_hours: float = 0) -> str:
    now = datetime.now(timezone.utc) + timedelta(hours=delta_hours)
    return now.isoformat()


def test_record_event_persists(settings_for_tests):
    ev = shd.record_event("occ", "success", status_code=200, duration_ms=120)
    stored = get_repository().get(shd.EVENTS_COLLECTION, ev.event_id)
    assert stored is not None
    assert stored["source_id"] == "occ"
    assert stored["outcome"] == "success"
    assert stored["status_code"] == 200


def test_record_event_rejects_unknown_outcome(settings_for_tests):
    with pytest.raises(ValueError):
        shd.record_event("occ", "weird")


def test_record_event_truncates_error(settings_for_tests):
    ev = shd.record_event("occ", "failure", error="X" * 1000)
    assert ev.error is not None
    assert len(ev.error) <= 500


def test_compose_digest_empty_window(settings_for_tests):
    digest = shd.compose_digest()
    assert digest.n_sources_seen == 0
    assert digest.n_flagged == 0


def test_compose_digest_groups_by_source(settings_for_tests):
    shd.record_event("occ", "success")
    shd.record_event("occ", "success")
    shd.record_event("occ", "failure")
    shd.record_event("fdic", "success")
    digest = shd.compose_digest()
    by_id = {r.source_id: r for r in digest.rows}
    assert by_id["occ"].success == 2
    assert by_id["occ"].failure == 1
    assert by_id["fdic"].success == 1
    assert by_id["fdic"].failure == 0


def test_high_failure_rate_flag(settings_for_tests):
    for _ in range(4):
        shd.record_event("occ", "failure")
    digest = shd.compose_digest()
    row = next(r for r in digest.rows if r.source_id == "occ")
    assert "high_failure_rate" in row.flags
    assert digest.by_flag.get("high_failure_rate") == 1


def test_circuit_open_flag(settings_for_tests):
    shd.record_event("occ", "circuit_open")
    digest = shd.compose_digest()
    row = next(r for r in digest.rows if r.source_id == "occ")
    assert "circuit_open" in row.flags


def test_never_succeeded_flag(settings_for_tests):
    # Single failure with no preceding success → never_succeeded.
    shd.record_event("occ", "failure")
    digest = shd.compose_digest()
    row = next(r for r in digest.rows if r.source_id == "occ")
    assert "never_succeeded" in row.flags


def test_stale_flag_when_last_success_old(settings_for_tests):
    # Plant an old success event by upserting directly with a past
    # timestamp, then a recent failure.
    repo = get_repository()
    stale_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    repo.upsert(shd.EVENTS_COLLECTION, "old-1", {
        "event_id": "old-1",
        "source_id": "occ",
        "outcome": "success",
        "fetched_at": stale_ts,
    })
    shd.record_event("occ", "failure")
    # Use a wide window so the old success is included.
    digest = shd.compose_digest(window_hours=24 * 30)
    row = next(r for r in digest.rows if r.source_id == "occ")
    assert "stale" in row.flags
    assert row.days_since_success is not None
    assert row.days_since_success >= 7


def test_disabled_flag_from_policy(monkeypatch, settings_for_tests):
    monkeypatch.setattr(
        shd.source_policy,
        "policy_for",
        lambda sid: {
            "source_id": sid,
            "tos_status": "disabled",
            "independence_class": "regulator",
        },
    )
    shd.record_event("foo", "disabled")
    digest = shd.compose_digest()
    row = next(r for r in digest.rows if r.source_id == "foo")
    assert "disabled" in row.flags


def test_render_text_empty_case(settings_for_tests):
    digest = shd.compose_digest()
    body = shd.render_text(digest)
    assert "Source health digest" in body
    assert "No flagged sources" in body


def test_render_text_includes_flagged_sources(settings_for_tests):
    for _ in range(4):
        shd.record_event("occ", "failure")
    digest = shd.compose_digest()
    body = shd.render_text(digest)
    assert "occ" in body
    assert "high_failure_rate" in body


def test_render_text_lists_flag_counts(settings_for_tests):
    shd.record_event("occ", "circuit_open")
    digest = shd.compose_digest()
    body = shd.render_text(digest)
    assert "circuit_open: 1" in body


def test_send_digest_default_sender_persists(settings_for_tests):
    shd.record_event("occ", "success")
    result = shd.send_digest()
    assert result["digest_id"].startswith("shd-")
    stored = get_repository().get(shd.DIGESTS_COLLECTION, result["digest_id"])
    assert stored is not None
    assert "Source health digest" in stored["body"]


def test_send_digest_with_custom_sender(settings_for_tests):
    calls: list[tuple] = []

    def sender(digest, body):
        calls.append((digest.digest_id, body))
        return {"sent": True, "digest_id": digest.digest_id}

    shd.record_event("occ", "success")
    result = shd.send_digest(sender=sender)
    assert result["sent"] is True
    assert len(calls) == 1
    assert "Source health digest" in calls[0][1]


def test_list_recent_digests_newest_first(settings_for_tests):
    shd.record_event("occ", "success")
    # First digest — explicit older timestamp.
    older = datetime.now(timezone.utc) - timedelta(days=1)
    shd.send_digest(generated_at=older)
    # Second digest — now.
    shd.send_digest()
    rows = shd.list_recent_digests()
    assert len(rows) >= 2
    assert rows[0]["generated_at"] >= rows[1]["generated_at"]


def test_failure_rate_threshold_requires_min_sample(settings_for_tests):
    # 2 failures, 1 success — failure rate 0.66 but only 3 samples, below
    # the minimum sample size of 4 — no high_failure_rate flag.
    shd.record_event("occ", "failure")
    shd.record_event("occ", "failure")
    shd.record_event("occ", "success")
    digest = shd.compose_digest()
    row = next(r for r in digest.rows if r.source_id == "occ")
    assert "high_failure_rate" not in row.flags


def test_window_excludes_events_outside_range(settings_for_tests):
    repo = get_repository()
    far_past = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    repo.upsert(shd.EVENTS_COLLECTION, "old-2", {
        "event_id": "old-2",
        "source_id": "occ",
        "outcome": "failure",
        "fetched_at": far_past,
    })
    # Window = 24 hours — the 30-day-old failure is excluded.
    digest = shd.compose_digest(window_hours=24)
    occ_rows = [r for r in digest.rows if r.source_id == "occ"]
    assert occ_rows == []
