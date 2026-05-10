"""Canonical-name resolution for clients / vendors / regulators.

Pipeline:
  1. exact alias match in entity_aliases.yml (preferred — config-controlled)
  2. fuzzy token match via rapidfuzz over the union of canonical names + aliases
     (threshold 88 by default; tunable per call)
  3. fallback: return the input unchanged + confidence=0
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz, process

log = logging.getLogger(__name__)

_CONFIG = Path(__file__).resolve().parents[3] / "config" / "entity_aliases.yml"


@dataclass
class Resolution:
    canonical: str
    confidence: float  # 0..100
    method: str  # "exact_alias" | "fuzzy" | "passthrough"
    kind: str  # "client" | "vendor" | "regulator"


@lru_cache(maxsize=1)
def _load_aliases() -> dict[str, dict[str, list[str]]]:
    import yaml
    if not _CONFIG.exists():
        return {"client": {}, "vendor": {}, "regulator": {}}
    raw = yaml.safe_load(_CONFIG.read_text()) or {}
    out: dict[str, dict[str, list[str]]] = raw.get("aliases", {})
    for k in ("client", "vendor", "regulator"):
        out.setdefault(k, {})
    return out


@lru_cache(maxsize=1)
def _alias_index(kind: str) -> dict[str, str]:
    """alias-string-lower → canonical-name."""
    aliases = _load_aliases().get(kind, {})
    out: dict[str, str] = {}
    for canonical, alts in aliases.items():
        out[canonical.lower()] = canonical
        for a in alts:
            out[a.lower()] = canonical
    return out


def resolve(name: str, kind: str = "client", fuzzy_threshold: int = 92) -> Resolution:
    if not name:
        return Resolution(canonical="", confidence=0, method="passthrough", kind=kind)
    s = name.strip()
    idx = _alias_index(kind)
    # exact alias hit
    if s.lower() in idx:
        return Resolution(canonical=idx[s.lower()], confidence=100.0, method="exact_alias", kind=kind)
    # fuzzy
    candidates = list(idx.keys())
    if not candidates:
        return Resolution(canonical=s, confidence=0, method="passthrough", kind=kind)
    match = process.extractOne(s.lower(), candidates, scorer=fuzz.WRatio)
    if match and match[1] >= fuzzy_threshold:
        return Resolution(canonical=idx[match[0]], confidence=float(match[1]), method="fuzzy", kind=kind)
    return Resolution(canonical=s, confidence=0, method="passthrough", kind=kind)


def known_entities(kind: str) -> list[str]:
    """Return the list of canonical names for a given kind."""
    return list(_load_aliases().get(kind, {}).keys())


def reset_cache_for_tests() -> None:
    _load_aliases.cache_clear()
    _alias_index.cache_clear()
