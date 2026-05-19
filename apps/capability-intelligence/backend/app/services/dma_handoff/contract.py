"""IMP-17 — DMA handoff contract.

The shape of the ``dma-handoff-v1`` packet emitted by
:func:`app.services.client_journey_service.dma_packet` is the source of
truth for what the Digital Maturity Assessor (DMA) consumes. Both
products import this module and run :func:`validate_dma_packet` in CI so
schema drift fails before reaching production.

Versioning rule:
    - Any breaking change MUST bump ``CONTRACT_SCHEMA_VERSION`` *and* a
      matching update lands in the DMA repo in the same PR. The contract
      bumps to ``dma-handoff-v2``, ``v3``, … as new fields become
      mandatory.
    - Optional fields can be added without a bump.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

CONTRACT_SCHEMA_VERSION = "dma-handoff-v1"


class ContractError(ValueError):
    """Raised when a packet violates the contract."""


@dataclass
class FieldSpec:
    name: str
    required: bool
    type: type | tuple[type, ...]
    description: str = ""


@dataclass
class DmaHandoffContract:
    schema_version: str = CONTRACT_SCHEMA_VERSION
    top_level: list[FieldSpec] = field(default_factory=list)
    engagement: list[FieldSpec] = field(default_factory=list)
    priority: list[FieldSpec] = field(default_factory=list)
    vendor: list[FieldSpec] = field(default_factory=list)


CONTRACT = DmaHandoffContract(
    top_level=[
        FieldSpec("schema_version", True, str, "must equal CONTRACT_SCHEMA_VERSION"),
        FieldSpec("generated_at", True, str, "ISO-8601 timestamp"),
        FieldSpec("client", True, str, "canonical client name"),
        FieldSpec("asset_size_usd_bn", False, (int, float, type(None))),
        FieldSpec("subverticals", True, list, "1+ subvertical ids"),
        FieldSpec("cohorts", True, list, "0+ cohort ids"),
        FieldSpec("engagement", True, dict, "active/prospect/inactive/archived counts"),
        FieldSpec("vendor_stack", True, list, "vendors known for this client"),
        FieldSpec("state_distribution", True, dict, "lifecycle state → count"),
        FieldSpec("priorities", True, list, "ranked priority list, ≤10"),
    ],
    engagement=[
        FieldSpec("active", True, int),
        FieldSpec("prospect", True, int),
        FieldSpec("inactive", True, int),
        FieldSpec("archived", True, int),
    ],
    priority=[
        FieldSpec("sub_cap_id", True, str),
        FieldSpec("sub_cap_name", True, str),
        FieldSpec("state", True, str),
        FieldSpec("score", True, (int, float)),
        FieldSpec("sow_count", True, int),
    ],
    vendor=[
        FieldSpec("vendor", True, str),
        FieldSpec("category", True, str),
        FieldSpec("confidence", True, (int, float)),
    ],
)


DMA_HANDOFF_FIXTURE: dict[str, Any] = {
    "schema_version": CONTRACT_SCHEMA_VERSION,
    "generated_at": "2026-05-19T08:00:00+00:00",
    "client": "Acme Financial",
    "asset_size_usd_bn": 120.5,
    "subverticals": ["retail-banking"],
    "cohorts": ["large-bank"],
    "engagement": {
        "active": 2,
        "prospect": 1,
        "inactive": 0,
        "archived": 0,
    },
    "vendor_stack": [
        {"vendor": "Salesforce", "category": "CRM", "confidence": 0.88},
    ],
    "state_distribution": {"rising": 4, "stable": 2, "emerging": 1},
    "priorities": [
        {
            "sub_cap_id": "P1C1.1.1",
            "sub_cap_name": "Digital Strategy Document",
            "state": "RISING",
            "score": 0.74,
            "sow_count": 3,
        }
    ],
}


# ─── Validation ─────────────────────────────────────────────────────────────


def _check_fields(
    payload: Mapping[str, Any], specs: list[FieldSpec], context: str
) -> list[str]:
    errors: list[str] = []
    for spec in specs:
        if spec.name not in payload:
            if spec.required:
                errors.append(f"{context}: missing required field '{spec.name}'")
            continue
        value = payload[spec.name]
        if not _type_ok(value, spec.type, allow_none=not spec.required):
            errors.append(
                f"{context}: field '{spec.name}' has type {type(value).__name__}, "
                f"expected {spec.type}"
            )
    return errors


def _type_ok(
    value: Any, expected: type | tuple[type, ...], *, allow_none: bool
) -> bool:
    if value is None:
        if allow_none:
            return True
        if isinstance(expected, tuple) and type(None) in expected:
            return True
        return False
    # bool is a subclass of int — but a boolean in an `int` slot is almost
    # always a bug. Reject it explicitly.
    if isinstance(value, bool) and not _expected_includes(expected, bool):
        return False
    if isinstance(expected, tuple):
        return isinstance(value, expected)
    return isinstance(value, expected)


def _expected_includes(expected: type | tuple[type, ...], cls: type) -> bool:
    if isinstance(expected, tuple):
        return cls in expected
    return expected is cls


def validate_dma_packet(packet: Mapping[str, Any]) -> None:
    """Raise :class:`ContractError` if ``packet`` violates the contract."""
    if not isinstance(packet, Mapping):
        raise ContractError(f"packet must be a dict, got {type(packet).__name__}")

    errors: list[str] = []

    # Top level.
    errors.extend(_check_fields(packet, CONTRACT.top_level, "top-level"))

    # schema_version must match.
    if packet.get("schema_version") not in (None, CONTRACT_SCHEMA_VERSION):
        errors.append(
            f"top-level: schema_version '{packet.get('schema_version')}' "
            f"does not match contract '{CONTRACT_SCHEMA_VERSION}'"
        )

    # Engagement sub-object.
    eng = packet.get("engagement")
    if isinstance(eng, Mapping):
        errors.extend(_check_fields(eng, CONTRACT.engagement, "engagement"))
        for k in ("active", "prospect", "inactive", "archived"):
            v = eng.get(k)
            if isinstance(v, int) and not isinstance(v, bool) and v < 0:
                errors.append(f"engagement.{k}: count must be ≥0, got {v}")

    # Priorities — at most 10, each conforming to the priority spec.
    priorities = packet.get("priorities")
    if isinstance(priorities, list):
        if len(priorities) > 10:
            errors.append(
                f"priorities: contains {len(priorities)} items, max 10"
            )
        for idx, prio in enumerate(priorities):
            if not isinstance(prio, Mapping):
                errors.append(f"priorities[{idx}]: must be a dict")
                continue
            errors.extend(_check_fields(prio, CONTRACT.priority, f"priorities[{idx}]"))
            score = prio.get("score")
            if isinstance(score, (int, float)) and not (0 <= score <= 1):
                errors.append(
                    f"priorities[{idx}].score: must be in [0, 1], got {score}"
                )
            state = prio.get("state")
            if isinstance(state, str) and state.upper() not in {
                "EMERGING", "RISING", "STABLE", "DECLINING", "FADING", "DEAD",
                "ACTIVE", "HIGH_VALUE", "DECAY", "INACTIVE", "PROPOSED", "RETIRED",
            }:
                errors.append(
                    f"priorities[{idx}].state: '{state}' not in canonical lifecycle vocabulary"
                )

    # Vendor stack.
    vendors = packet.get("vendor_stack")
    if isinstance(vendors, list):
        for idx, vend in enumerate(vendors):
            if not isinstance(vend, Mapping):
                errors.append(f"vendor_stack[{idx}]: must be a dict")
                continue
            errors.extend(_check_fields(vend, CONTRACT.vendor, f"vendor_stack[{idx}]"))
            conf = vend.get("confidence")
            if isinstance(conf, (int, float)) and not (0 <= conf <= 1):
                errors.append(
                    f"vendor_stack[{idx}].confidence: must be in [0, 1], got {conf}"
                )

    # subverticals must be a list (may be empty if the client's SOWs
    # didn't ship a subvertical tag — DMA tolerates that case).
    subs = packet.get("subverticals")
    if subs is not None and not isinstance(subs, list):
        errors.append("subverticals: must be a list")

    if errors:
        raise ContractError("; ".join(errors))
