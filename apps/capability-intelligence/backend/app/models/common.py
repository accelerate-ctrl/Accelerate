"""Common enums + schema-version registry.

Every Firestore collection + Pydantic model in the system carries a
``_schema_version`` so future migrations are traceable. The registry
below is the single source of truth; bump the value when a breaking
change ships, and add a migration test in
``tests/unit/test_schema_versions.py`` against historical fixtures.
"""

from enum import Enum


class ClaimLabel(str, Enum):
    FACT = "FACT"
    INFERENCE = "INFERENCE"
    HYPOTHESIS = "HYPOTHESIS"
    CEILING_ESTIMATE = "CEILING_ESTIMATE"


class SourceTier(str, Enum):
    T1 = "T1"  # primary regulators / official partner platform
    T2 = "T2"  # trade publications / analyst & strategy firms (cited)
    T3 = "T3"  # ESG / AI research
    T4 = "T4"  # technographic signals
    T5 = "T5"  # vendor self-promotion / press releases


class LifecycleState(str, Enum):
    """Market-signal lifecycle vocabulary (PRD v2.0 D4).

    Replaces the curation-axis values (ACTIVE/HIGH_VALUE/DECAY/etc.) that
    leaked from the v14 schema. The values match the strings produced by
    :mod:`app.services.lifecycle_service` and consumed by the frontend
    Lifecycle Manager kanban.
    """
    EMERGING = "EMERGING"
    RISING = "RISING"
    STABLE = "STABLE"
    DECLINING = "DECLINING"
    FADING = "FADING"
    DEAD = "DEAD"


class SubVertical(str, Enum):
    """9 canonical subverticals (PRD D19).

    BK + RB are merged into Retail Banking; WM + AM are merged into
    Wealth & Asset Management. IB is Insurance Brokerages.
    """
    RB = "RB"   # Retail Banking (incl. former BK)
    CB = "CB"   # Commercial Banking
    CR = "CR"   # Credit Unions
    CM = "CM"   # Capital Markets
    WAM = "WAM"  # Wealth & Asset Management (incl. former WM + AM)
    IN = "IN"   # Insurance Carriers
    IB = "IB"   # Insurance Brokerages
    PI = "PI"   # PayTech & FinTech
    LS = "LS"   # Lending Services


class PersonaFamily(str, Enum):
    """5 persona families per PRD §4 / App Flow §3.3."""
    C_SUITE = "c_suite"
    OPERATIONS = "operations"
    TECHNOLOGY = "technology"
    RISK_COMPLIANCE = "risk_compliance"
    FRONTLINE = "frontline"


class LeverageTier(str, Enum):
    """Consultant-loop leverage tiers (PRD §6.1)."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    COMMIT = "COMMIT"
    DIGEST = "DIGEST"


class MaturityLevel(str, Enum):
    M1 = "M1"
    M2 = "M2"
    M3 = "M3"
    M4 = "M4"
    M5 = "M5"


# ─── Schema-version registry ────────────────────────────────────────────────
#
# Single source of truth for every persisted-row schema version.
# Every domain row written to the repository carries
# ``_schema_version`` from this map; bump the version when a breaking
# change ships and add a migration test against fixture rows.

SCHEMA_VERSIONS: dict[str, str] = {
    # Catalogue spine (Batch 1)
    "subcap": "subcap-v1",
    "category": "category-v1",
    "l1_capability": "l1-v1",
    "use_case": "use-case-v1",
    "l3_platform": "l3-v1",
    "l4_feature": "l4-v1",
    "maturity_descriptor": "maturity-v1",
    "theme": "theme-v1",
    "vc_mapping": "vc-mapping-v1",
    "story": "story-v1",
    "version": "version-v1",
    # Internal evidence (Batch 3)
    "sow": "sow-v1",
    "sow_chunk": "sow-chunk-v1",
    "sow_mention": "sow-mention-v1",
    "story_canonical": "story-canonical-v1",
    "client": "client-v1",
    # LLM core (Batch 4)
    "reasoning_chain": "reasoning-chain-v1",
    "suggestion": "suggestion-v1",
    "validation_gate_run": "gate-run-v1",
    "news_item": "news-item-v1",
    "trend_item": "trend-item-v1",
    # Benchmarks (Batch 5)
    "benchmark_observation": "benchmark-observation-v1",
    "benchmark_distribution": "benchmark-distribution-v1",
    "benchmark_cohort": "benchmark-cohort-v1",
    # Synthesis (Batch 6)
    "lifecycle_score": "lifecycle-score-v1",
    "lifecycle_transition": "lifecycle-transition-v1",
    "vendor_profile": "vendor-profile-v1",
    "vendor_adoption": "vendor-adoption-v1",
    "client_journey": "client-journey-v1",
    "dma_packet": "dma-handoff-v1",
    # Digest + audit (Batch 7)
    "strategic_digest": "strategic-digest-v1",
    "digest_priority": "digest-priority-v1",
    "audit_report": "audit-report-v1",
    # Operator surface (Batch 8)
    "chat_conversation": "chat-conversation-v1",
    "what_if_simulation": "what-if-simulation-v1",
    "notification": "notification-v1",
    "eval_run": "eval-run-v1",
    # Production hardening (Batch 9)
    "reproducibility_manifest": "manifest-v1",
    # Audit-fix additions
    "capability_cluster": "cluster-v1",
    "delta_report": "delta-report-v1",
    "graph_snapshot_shard": "graph-shard-v1",
    # Phase 1 — v7.0 schema alignment
    "persona_ref": "persona-ref-v1",
    "canonical_entity": "canonical-entity-v1",
}


def schema_version(key: str) -> str:
    """Lookup a schema version; raises KeyError if unregistered (forces explicit registration)."""
    return SCHEMA_VERSIONS[key]
