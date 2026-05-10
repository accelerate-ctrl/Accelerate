"""Cloud Run Job: sow_full_reindex.

Force-rebuilds every SOW row including chunks + mentions. Weekly
cadence in production; same call as sow_incremental but logs the
intent so operators can distinguish in audit reports.
"""

from __future__ import annotations

from ..observability import structured_log
from .sow_incremental import run as _run_inner


def run() -> dict:
    structured_log("sow.reindex.start", reason="weekly full re-ingest")
    out = _run_inner()
    structured_log("sow.reindex.done", **{k: out.get(k) for k in ("sows_loaded", "chunks_total", "mentions_total")})
    return out
