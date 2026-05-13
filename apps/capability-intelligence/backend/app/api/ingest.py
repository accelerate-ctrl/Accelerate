"""Unified `Pull all sources` endpoint.

Fans out to every source ingest (catalogue, SOWs, stories, news, vendors,
benchmarks, client-journeys) and returns a per-source result so the UI
can show what succeeded vs what failed.

Each ingest is wrapped in try/except so one failing source (e.g. Jira
creds not set, or a Drive folder not shared with the SA) doesn't break
the others — the failure is surfaced in the response.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends

from ..deps import auth_dep

router = APIRouter()
log = logging.getLogger(__name__)


def _safe(name: str, fn) -> dict[str, Any]:
    """Run an ingest, return {ok, name, result|error}."""
    try:
        result = fn()
        return {"ok": True, "source": name, "result": _normalise(result)}
    except Exception as exc:  # noqa: BLE001 — boundary handler
        log.exception("ingest %s failed", name)
        return {"ok": False, "source": name, "error": f"{type(exc).__name__}: {exc}"}


def _normalise(r: Any) -> dict:
    """Dataclasses → dict, drop bytes/datetime to plain JSON-safe values."""
    if isinstance(r, dict):
        return {k: _scalar(v) for k, v in r.items()}
    if hasattr(r, "__dict__"):
        return {k: _scalar(v) for k, v in vars(r).items() if not k.startswith("_")}
    return {"value": _scalar(r)}


def _scalar(v: Any) -> Any:
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, (list, tuple)):
        return [_scalar(x) for x in v][:20]
    if isinstance(v, dict):
        return {str(k): _scalar(val) for k, val in list(v.items())[:20]}
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)[:200]


@router.post("/refresh-all")
def refresh_all(user=Depends(auth_dep)) -> dict:
    """Trigger every source ingest in parallel-ish order (sequential but
    fast-fail per source so the UI sees results streaming in)."""
    from ..services import (
        benchmarks_service,
        catalogue_service,
        client_journey_service,
        news_service,
        sow_service,
        stories_service,
        vendor_intel_service,
    )

    results = [
        _safe("catalogue",       lambda: catalogue_service.refresh_all_pillars(by=user.email)),
        _safe("sows",            lambda: sow_service.ingest_all(by=user.email)),
        _safe("stories",         lambda: stories_service.refresh_all(by=user.email)),
        _safe("news",            lambda: news_service.refresh()),
        _safe("vendors",         lambda: vendor_intel_service.refresh()),
        _safe("benchmarks",      lambda: benchmarks_service.refresh()),
        _safe("client_journeys", lambda: client_journey_service.refresh_all()),
    ]
    n_ok = sum(1 for r in results if r["ok"])
    return {
        "triggered_by": user.email,
        "sources_total": len(results),
        "sources_succeeded": n_ok,
        "sources_failed": len(results) - n_ok,
        "results": results,
    }
