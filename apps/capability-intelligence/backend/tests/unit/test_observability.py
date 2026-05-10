"""Observability + event bus — dev-mode no-op + structured logs."""

import io
import logging

from app.observability import emit_span, install_telemetry, structured_log
from app.services import event_bus


def test_install_telemetry_skips_without_endpoint(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    from app.main import create_app

    app = create_app()
    # No exception, no exporter installed.
    assert install_telemetry(app) is False


def test_emit_span_falls_back_to_structured_log_in_dev(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    # Should not raise + should not require the OTel SDK to be installed
    with emit_span("test-span", attr1="x"):
        pass


def test_structured_log_does_not_raise():
    structured_log("test.event", foo="bar", n=42)


def test_event_bus_dev_mode_logs(monkeypatch, settings_for_tests):
    monkeypatch.setenv("USE_GCP", "false")
    from app.config import get_settings
    get_settings.cache_clear()
    # Should not raise + does not need google-cloud-pubsub installed
    event_bus.publish_event("job.completed", {"job": "news_poll", "status": "ok"})


def test_event_bus_topic_map():
    assert event_bus.topic_for("job.completed") == "job-events"
    assert event_bus.topic_for("audit.critical_finding") == "audit-events"
    assert event_bus.topic_for("lifecycle.transitioned") == "lifecycle-events"
    assert event_bus.topic_for("digest.generated") == "digest-events"
    # unknown event falls through to a default topic
    assert event_bus.topic_for("not-a-known-event") == "default-events"


def test_event_bus_skipped_when_use_gcp_set_but_no_project(monkeypatch, settings_for_tests):
    monkeypatch.setenv("USE_GCP", "true")
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
    from app.config import get_settings
    get_settings.cache_clear()
    # Should still not raise — logs a warning + drops the event
    event_bus.publish_event("job.completed", {"job": "x"})
