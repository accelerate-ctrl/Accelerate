"""Operational policy loader for canonical sources.

Per QA_AUDIT.md fix #14. The base ``config/canonical_sources.yml`` is
URL+tier static; this module layers in the operational fields
(``tos_status``, ``independence_class``, rate limits, circuit-breaker
state) from the sidecar ``canonical_sources_policy.yml``.

Public surface
--------------
    policy_for(source_id) -> dict
    is_disabled(source_id) -> bool
    independence_class(source_id) -> str
    rate_limits(source_id) -> dict
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml

_CONFIG_DIR = Path(__file__).resolve().parents[3] / "config"
_POLICY_FILE = "canonical_sources_policy.yml"


@functools.lru_cache(maxsize=1)
def _load_policy() -> dict[str, Any]:
    p = _CONFIG_DIR / _POLICY_FILE
    if not p.exists():
        return {"default": {}, "overrides": {}}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {"default": {}, "overrides": {}}


def policy_for(source_id: str) -> dict[str, Any]:
    """Merged policy: default ⊕ override."""
    p = _load_policy()
    out = dict(p.get("default") or {})
    overrides = (p.get("overrides") or {}).get(source_id) or {}
    out.update(overrides)
    out["source_id"] = source_id
    return out


def is_disabled(source_id: str) -> bool:
    return policy_for(source_id).get("tos_status") == "disabled"


def independence_class(source_id: str) -> str:
    return policy_for(source_id).get("independence_class", "regulator")


def rate_limits(source_id: str) -> dict[str, Any]:
    pol = policy_for(source_id)
    return {
        "max_requests_per_minute": pol.get("max_requests_per_minute", 10),
        "max_concurrent": pol.get("max_concurrent", 2),
        "backoff_policy": pol.get("backoff_policy", "exponential"),
        "retry_after_respect": pol.get("retry_after_respect", True),
    }


def circuit_breaker_config(source_id: str) -> dict[str, Any]:
    pol = policy_for(source_id)
    return {
        "consecutive_failure_threshold": pol.get("cb_consecutive_failure_threshold", 5),
        "open_duration_seconds": pol.get("cb_open_duration_seconds", 3600),
    }
