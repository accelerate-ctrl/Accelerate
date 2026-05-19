"""Prompt YAML loader (IMP-6).

Moves all LLM prompts from inline Python strings to versioned YAML
files under ``prompts/{operation}/v{n}.yaml``. Each prompt has:

- ``version`` (semver-ish string, e.g. ``v1``, ``v1.2``).
- ``system`` — system prompt sent to the model.
- ``user_template`` — user prompt with ``{placeholder}`` slots.
- ``model`` — default model for this prompt (overridable at call site).
- ``output_schema`` — JSON schema the response must satisfy.
- ``regression_dataset`` — reference to a golden dataset that gates
  prompt-version promotion.

Benefits per Implementation Steps §3 IMP-6:

1. Prompt changes ship without a code deploy — just upload a new YAML.
2. A/B testing — two prompt versions run side-by-side under feature
   flags.
3. Per-prompt regression tests — CI gates the prompt against its
   reference golden dataset before promotion.
4. Roll back to the previous version by renaming the active pointer.

Loader behaviour:

- Reads from ``config/prompts/{operation}/`` by default; opt-in via
  ``PROMPTS_DIR`` env var to point at a staging copy.
- Selects the *active* version recorded in ``active.yaml`` (a single-
  field doc: ``version: v2``). Falls back to the highest version
  number on disk if no ``active.yaml`` exists.
- Caches loaded prompts in-process so repeated calls don't re-read
  the disk; ``reload()`` is the test hook to clear the cache.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


# Default location relative to the backend package root.
_DEFAULT_PROMPTS_DIR = (
    Path(__file__).resolve().parents[2] / "config" / "prompts"
)


@dataclass
class PromptSpec:
    """One loaded prompt spec."""

    operation: str
    version: str
    system: str
    user_template: str
    model: str | None = None
    output_schema: dict[str, Any] | None = None
    regression_dataset: str | None = None
    metadata: dict[str, Any] | None = None


# In-process cache keyed by (operation, version). Cleared via reload().
_CACHE: dict[tuple[str, str], PromptSpec] = {}
_ACTIVE_VERSION_CACHE: dict[str, str] = {}


def _prompts_dir() -> Path:
    raw = os.environ.get("PROMPTS_DIR")
    if raw:
        return Path(raw)
    return _DEFAULT_PROMPTS_DIR


def _version_key(name: str) -> tuple[int, int]:
    """Sort key so ``v1.10`` comes after ``v1.9``.

    Accepts ``v1``, ``v1.2``, ``v1.2.3`` (later segments ignored beyond
    the first two for sort purposes).
    """
    m = re.match(r"^v?(\d+)(?:\.(\d+))?", name)
    if not m:
        return (0, 0)
    return (int(m.group(1)), int(m.group(2) or 0))


def _resolve_active_version(operation: str) -> str:
    """Return the active version id for an operation.

    Reads ``{operation}/active.yaml`` if present; otherwise picks the
    highest-numbered version file on disk. Raises ``FileNotFoundError``
    when the operation directory doesn't exist.
    """
    if operation in _ACTIVE_VERSION_CACHE:
        return _ACTIVE_VERSION_CACHE[operation]
    op_dir = _prompts_dir() / operation
    if not op_dir.is_dir():
        raise FileNotFoundError(f"prompt operation not found: {operation}")
    active_file = op_dir / "active.yaml"
    if active_file.is_file():
        try:
            payload = yaml.safe_load(active_file.read_text(encoding="utf-8")) or {}
            v = str(payload.get("version") or "").strip()
            if v:
                _ACTIVE_VERSION_CACHE[operation] = v
                return v
        except Exception:
            logger.exception("failed to parse active.yaml for %s", operation)
    # Fallback: highest version on disk.
    versions: list[str] = []
    for p in op_dir.glob("v*.yaml"):
        if p.name == "active.yaml":
            continue
        versions.append(p.stem)
    if not versions:
        raise FileNotFoundError(f"no prompt versions for operation: {operation}")
    versions.sort(key=_version_key, reverse=True)
    _ACTIVE_VERSION_CACHE[operation] = versions[0]
    return versions[0]


def load(operation: str, *, version: str | None = None) -> PromptSpec:
    """Load a prompt spec from disk.

    - ``operation``: name of the operation directory.
    - ``version``: explicit version (e.g., ``v2``); when omitted, the
      active pointer is used.
    """
    actual_version = version or _resolve_active_version(operation)
    cache_key = (operation, actual_version)
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    fpath = _prompts_dir() / operation / f"{actual_version}.yaml"
    if not fpath.is_file():
        raise FileNotFoundError(
            f"prompt file not found: {operation}/{actual_version}.yaml",
        )
    payload = yaml.safe_load(fpath.read_text(encoding="utf-8")) or {}
    system = payload.get("system") or ""
    user_template = payload.get("user_template") or ""
    if not user_template:
        raise ValueError(
            f"prompt {operation}/{actual_version} missing required `user_template`",
        )
    spec = PromptSpec(
        operation=operation,
        version=actual_version,
        system=str(system),
        user_template=str(user_template),
        model=payload.get("model"),
        output_schema=payload.get("output_schema"),
        regression_dataset=payload.get("regression_dataset"),
        metadata=payload.get("metadata"),
    )
    _CACHE[cache_key] = spec
    return spec


def render(operation: str, *, version: str | None = None, **kwargs) -> tuple[str, str, PromptSpec]:
    """Load + format a prompt. Returns ``(system, user_text, spec)``.

    Missing placeholders raise ``KeyError`` with a helpful message so
    a typo in the call site fails fast instead of producing a
    half-rendered prompt the LLM has to interpret.
    """
    spec = load(operation, version=version)
    try:
        user_text = spec.user_template.format(**kwargs)
    except KeyError as exc:
        missing = exc.args[0]
        raise KeyError(
            f"prompt {operation}/{spec.version} requires placeholder "
            f"{{{missing}}} but it was not provided in the render() call",
        ) from None
    return spec.system, user_text, spec


def list_operations() -> list[str]:
    """All operations with at least one prompt file on disk."""
    root = _prompts_dir()
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def list_versions(operation: str) -> list[str]:
    """All version files for an operation, sorted highest first."""
    op_dir = _prompts_dir() / operation
    if not op_dir.is_dir():
        return []
    versions = [
        p.stem for p in op_dir.glob("v*.yaml") if p.name != "active.yaml"
    ]
    versions.sort(key=_version_key, reverse=True)
    return versions


def reload() -> None:
    """Drop the in-process cache. Used by tests that flip ``PROMPTS_DIR``
    mid-run; also called when an admin commits a new prompt version.
    """
    _CACHE.clear()
    _ACTIVE_VERSION_CACHE.clear()


__all__ = [
    "PromptSpec",
    "list_operations",
    "list_versions",
    "load",
    "reload",
    "render",
]
