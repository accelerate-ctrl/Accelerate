"""IMP-13 — daily source-health digest Cloud Run Job."""

from __future__ import annotations

import json
from io import BytesIO

import pytest

from app.jobs import runner, source_health_digest_daily
from app.services import source_health_digest


def test_runner_recognises_job():
    assert "source_health_digest_daily" in runner.ALL_JOBS


def test_run_uses_repo_sender_without_webhook(monkeypatch, settings_for_tests):
    monkeypatch.delenv(source_health_digest_daily.WEBHOOK_ENV, raising=False)
    monkeypatch.delenv("SOURCE_HEALTH_WINDOW_HOURS", raising=False)
    source_health_digest.record_event("occ", "success")
    out = source_health_digest_daily.run()
    assert out["digest_id"].startswith("shd-")
    assert out["transport"] == "repository"


def test_run_with_webhook_posts(monkeypatch, settings_for_tests):
    posted: list[dict] = []

    class FakeResp:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def read(self):
            return b""

    def fake_urlopen(req, timeout=None):
        posted.append({"url": req.full_url, "body": req.data.decode("utf-8")})
        return FakeResp()

    monkeypatch.setattr(
        "app.jobs.source_health_digest_daily.request.urlopen", fake_urlopen
    )
    monkeypatch.setenv(
        source_health_digest_daily.WEBHOOK_ENV,
        "https://hooks.example.com/services/T/B/C",
    )
    source_health_digest.record_event("occ", "circuit_open")
    out = source_health_digest_daily.run()
    assert out["transport"] == "webhook"
    assert out["webhook_status"] == 200
    assert len(posted) == 1
    body = json.loads(posted[0]["body"])
    assert "text" in body
    assert "Source health digest" in body["text"]


def test_run_handles_webhook_failure(monkeypatch, settings_for_tests):
    from urllib.error import URLError

    def boom(req, timeout=None):
        raise URLError("connection refused")

    monkeypatch.setattr(
        "app.jobs.source_health_digest_daily.request.urlopen", boom
    )
    monkeypatch.setenv(
        source_health_digest_daily.WEBHOOK_ENV,
        "https://hooks.example.com/x",
    )
    source_health_digest.record_event("occ", "success")
    out = source_health_digest_daily.run()
    assert "webhook_error" in out


def test_window_hours_env_override(monkeypatch, settings_for_tests):
    monkeypatch.delenv(source_health_digest_daily.WEBHOOK_ENV, raising=False)
    monkeypatch.setenv("SOURCE_HEALTH_WINDOW_HOURS", "1")
    source_health_digest.record_event("occ", "success")
    out = source_health_digest_daily.run()
    # window_hours=1 → window_start is ~1h ago.
    assert out["digest_id"].startswith("shd-")


def test_runner_dispatches_job(settings_for_tests):
    result = runner.execute("source_health_digest_daily")
    assert result["status"] == "ok"
    assert result["job"] == "source_health_digest_daily"
