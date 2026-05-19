"""DMA handoff package — Phase 5 contract tests (IMP-17).

The Capability Intelligence Agent emits a ``dma-handoff-v1`` packet that is
consumed by the Digital Maturity Assessor app. Both sides must agree on
the packet schema; if either drifts, the downstream DMA flow silently
breaks. This package owns the contract — a self-contained schema + a
validator that both products import and run in their own CI.
"""

from .contract import (
    CONTRACT_SCHEMA_VERSION,
    DMA_HANDOFF_FIXTURE,
    ContractError,
    DmaHandoffContract,
    validate_dma_packet,
)

__all__ = [
    "CONTRACT_SCHEMA_VERSION",
    "DMA_HANDOFF_FIXTURE",
    "ContractError",
    "DmaHandoffContract",
    "validate_dma_packet",
]
