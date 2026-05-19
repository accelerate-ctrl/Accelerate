"""Cloud Run Job: source_health_digest_daily (IMP-13).

Runs at 08:00 UTC every day. Composes the per-source health digest over
the last 24 hours and ships it via the configured sender. The default
sender persists the rendered body to ``source_health_digests`` so the
QA Dashboard always surfaces today's run, even when no email transport
is wired (the Phase 5 baseline).

When ``SOURCE_HEALTH_DIGEST_WEBHOOK_URL`` is set, the job additionally
POSTs the digest body to that URL (Slack-compatible). Auth-less webhooks
are accepted because the body contains no PII — just per-source counts
and policy metadata.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any
from urllib import error, request

from ..services import source_health_digest

logger = logging.getLogger(__name__)

WINDOW_HOURS_DEFAULT = 24
WEBHOOK_ENV = "SOURCE_HEALTH_DIGEST_WEBHOOK_URL"


def _webhook_sender(digest, body: str) -> dict[str, Any]:
    """POST the digest to the configured webhook + persist locally."""
    url = os.environ.get(WEBHOOK_ENV)
    payload = source_health_digest._repo_sender(digest, body)
    if not url:
        return payload
    try:
        req = request.Request(
            url,
            data=json.dumps({"text": body}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=10) as resp:  # noqa: S310
            payload["transport"] = "webhook"
            payload["webhook_status"] = resp.status
    except error.URLError as exc:
        logger.warning("source_health_digest webhook failed: %s", exc)
        payload["webhook_error"] = str(exc)[:200]
    return payload


def run(window_hours: int | None = None) -> dict[str, Any]:
    hours = int(os.environ.get("SOURCE_HEALTH_WINDOW_HOURS") or window_hours or WINDOW_HOURS_DEFAULT)
    sender = _webhook_sender if os.environ.get(WEBHOOK_ENV) else source_health_digest._repo_sender
    return source_health_digest.send_digest(window_hours=hours, sender=sender)
