"""Event bus — Pub/Sub publish with dev-mode no-op.

Per spec §20 / ARCHITECTURE Batch 9.

In production (``USE_GCP=true`` + ``GCP_PROJECT_ID``), publishes JSON
events to a Pub/Sub topic.  In dev (default), the publish is a structured
log line only — no SDK import, no network call.

Topic conventions (one per event family):

    job-events            job.completed, job.failed
    audit-events          audit.critical_finding
    lifecycle-events      lifecycle.transitioned
    digest-events         digest.generated
    suggestion-events     suggestion.applied, suggestion.rejected

Failed Pub/Sub publishes are logged + dropped (never raise).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from ..config import get_settings
from ..observability import structured_log

logger = logging.getLogger(__name__)

# event-name → topic mapping
_TOPIC_MAP: dict[str, str] = {
    "job.completed": "job-events",
    "job.failed": "job-events",
    "audit.critical_finding": "audit-events",
    "lifecycle.transitioned": "lifecycle-events",
    "digest.generated": "digest-events",
    "suggestion.applied": "suggestion-events",
    "suggestion.rejected": "suggestion-events",
}


def topic_for(event: str) -> str:
    return _TOPIC_MAP.get(event, "default-events")


def publish_event(event: str, payload: dict[str, Any]) -> None:
    """Publish a single event.  Always succeeds (errors logged + dropped)."""
    s = get_settings()
    enriched = {
        "event_name": event,
        "topic": topic_for(event),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }
    if not s.use_gcp:
        structured_log("event.published", **enriched, sink="dev-no-op")
        return

    if not s.gcp_project_id:
        structured_log(
            "event.skipped", reason="gcp_project_id not set", level="warning",
            **enriched,
        )
        return

    try:
        from google.cloud import pubsub_v1  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        structured_log(
            "event.import_failed", reason=str(exc), level="warning", **enriched,
        )
        return

    try:
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(s.gcp_project_id, topic_for(event))
        future = publisher.publish(topic_path, json.dumps(enriched).encode("utf-8"))
        future.result(timeout=10)
        structured_log("event.published", sink="pubsub", **enriched)
    except Exception as exc:  # noqa: BLE001
        structured_log(
            "event.publish_failed", reason=str(exc), level="error", **enriched,
        )
