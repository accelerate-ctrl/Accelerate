"""Cloud Run Job: citation_verify_daily.

Re-probes every cited URL in `citation_probes` whose 24-hour TTL has
expired. Marks dead links so the downstream gates can flag claims that
rely on them. Daily cadence.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..services.citation_verifier import verify_citation
from ..services.repository import get_repository

CUTOFF_HOURS = 24


def run() -> dict:
    repo = get_repository()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=CUTOFF_HOURS)
    probed = 0
    failed = 0
    with repo.defer_persist():
        for rec in repo.list("citation_probes"):
            checked = rec.get("checked_at")
            try:
                last = datetime.fromisoformat((checked or "").replace("Z", "+00:00"))
                if last and last > cutoff:
                    continue
            except Exception:
                pass
            url = rec.get("url")
            if not url:
                continue
            result = verify_citation({"url": url})
            probed += 1
            if not result.ok:
                failed += 1
    return {"probed": probed, "failed": failed}
