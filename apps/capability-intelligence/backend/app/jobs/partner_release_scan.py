"""Cloud Run Job: partner_release_scan.

Walks the six Zennify partners declared in `config/partners.yml`, pulls
the most recent release-notes entries (RSS where available, seed file
otherwise), extracts features via Gemini Flash, maps each to an L1
capability via 256-d cosine similarity, and emits two artefacts:

  * `partner_releases` — full record per release entry
  * `suggestions`      — `partner_feature_add` rows for high-confidence
                         catalogue gaps

Scheduled daily by Cloud Scheduler:
    cron: 0 7 * * *   # 07:00 UTC

Cost guardrail: capped at 25 entries × 6 partners = 150 Gemini Flash
calls per run (≈ $0.05/day at standard pricing).
"""

from __future__ import annotations

from ..services import partner_intel_service


def run() -> dict:
    return partner_intel_service.run_scan()
