"""Embedded QA — every analytical emit self-tests before persistence.

Per QA_AUDIT.md §4.4 / cross-cutting audit item.

Every domain object that the agent emits (digest, suggestion, reasoning
chain, benchmark distribution, client journey, DMA packet, audit
report, eval run) must run a list of contract checks against itself
before being written to the repository.  Failures are persisted with
``self_test_passed=False`` so the QA dashboard can surface them; the
caller decides whether to also raise.

Public surface
--------------

    Check                 dataclass — single rule outcome
    EmbeddedQAResult      dataclass — bundled checks + summary
    run_self_test         the workhorse function
    require_self_test     decorator that auto-attaches the result
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterable

# A check is (name, predicate, failure-detail-when-False).
CheckSpec = tuple[str, Callable[[dict], bool], str]


@dataclass
class Check:
    name: str
    passed: bool
    detail: str | None = None


@dataclass
class EmbeddedQAResult:
    self_test_passed: bool
    self_test_log: list[Check] = field(default_factory=list)
    schema_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "self_test_passed": self.self_test_passed,
            "self_test_log": [asdict(c) for c in self.self_test_log],
            "schema_version": self.schema_version,
        }


def run_self_test(
    payload: dict,
    checks: Iterable[CheckSpec],
    *,
    schema_version: str = "",
) -> EmbeddedQAResult:
    """Run a batch of contract checks against ``payload``.

    Each check is a ``(name, predicate, detail)`` triple.  Predicate
    receives the payload dict; if it raises we treat that as a fail.
    Always returns a result; never raises.
    """
    log: list[Check] = []
    for name, predicate, detail in checks:
        try:
            ok = bool(predicate(payload))
        except Exception as exc:  # noqa: BLE001
            ok = False
            detail = f"{detail or ''} [predicate raised: {exc}]"
        log.append(Check(name=name, passed=ok, detail=None if ok else detail))
    return EmbeddedQAResult(
        self_test_passed=all(c.passed for c in log),
        self_test_log=log,
        schema_version=schema_version,
    )


# ─── common reusable checks ────────────────────────────────────────────────


def has_keys(*keys: str) -> CheckSpec:
    """Every key must be present and not None."""
    keys_list = list(keys)
    return (
        f"has_keys({','.join(keys_list)})",
        lambda p: all(p.get(k) is not None for k in keys_list),
        f"required keys missing: {keys_list}",
    )


def non_empty_list(key: str, *, min_len: int = 1) -> CheckSpec:
    return (
        f"non_empty_list({key}, ≥{min_len})",
        lambda p: isinstance(p.get(key), list) and len(p[key]) >= min_len,
        f"{key} must be a list with ≥{min_len} items",
    )


def number_in_range(key: str, lo: float, hi: float) -> CheckSpec:
    def _check(p: dict) -> bool:
        v = p.get(key)
        return isinstance(v, (int, float)) and lo <= float(v) <= hi
    return (
        f"number_in_range({key},[{lo},{hi}])",
        _check,
        f"{key} must be a number in [{lo}, {hi}]",
    )
