"""Cloud Run Job: sow_incremental.

Re-runs the SOW ingest pipeline. The Drive discovery layer dedupes by
file_uri so same-file re-runs are no-ops; only newly added SOWs land
in Firestore. Hourly cadence.
"""

from __future__ import annotations

from dataclasses import asdict

from ..services import sow_service


def run() -> dict:
    result = sow_service.ingest_all(by="cron")
    return _serialise(result)


def _serialise(result) -> dict:
    out = {}
    for k, v in asdict(result).items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out
