"""Citation verifier — URL HEAD probe with daily cache.

In live mode this issues a real HEAD request via httpx (timeout 5s); in
dev mode it short-circuits to ``ok=True`` for any non-empty URL so tests
are hermetic.  Results are cached in the ``citation_probes`` collection
keyed by URL with a 24-hour TTL.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ..config import get_settings
from .repository import get_repository

logger = logging.getLogger(__name__)

PROBE_COLLECTION = "citation_probes"
TTL_HOURS = 24


@dataclass
class ProbeResult:
    url: str
    ok: bool
    status_code: int | None
    checked_at: str
    error: str | None = None


def verify_citation(source: dict) -> ProbeResult:
    url = source.get("url") or ""
    if not url:
        return ProbeResult(url="", ok=False, status_code=None, checked_at=_now(), error="no url")

    repo = get_repository()
    cached = repo.get(PROBE_COLLECTION, _key(url))
    if cached and not _expired(cached["checked_at"]):
        return ProbeResult(**{k: cached[k] for k in ProbeResult.__dataclass_fields__})

    s = get_settings()
    if not s.llm_live_mode:
        # dev: trust the URL; live mode HEADs it
        result = ProbeResult(url=url, ok=True, status_code=200, checked_at=_now())
    else:
        try:
            import httpx  # type: ignore
            r = httpx.head(url, timeout=5.0, follow_redirects=True)
            ok = 200 <= r.status_code < 400
            result = ProbeResult(url=url, ok=ok, status_code=r.status_code, checked_at=_now())
        except Exception as exc:  # noqa: BLE001
            logger.warning("citation probe failed for %s: %s", url, exc)
            result = ProbeResult(url=url, ok=False, status_code=None, checked_at=_now(), error=str(exc))

    repo.upsert(PROBE_COLLECTION, _key(url), result.__dict__)
    return result


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _expired(iso: str) -> bool:
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:
        return True
    return datetime.now(timezone.utc) - t > timedelta(hours=TTL_HOURS)


def _key(url: str) -> str:
    import hashlib
    return hashlib.sha256(url.encode()).hexdigest()
