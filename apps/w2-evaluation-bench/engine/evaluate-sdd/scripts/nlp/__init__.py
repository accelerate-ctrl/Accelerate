"""nlp — the deterministic pre-intelligence layer (v1.1 / engine v4.7+preintel).

Turns the server from a pure orchestrator into a pre-processing engine: it
parses the BRD/SDD into structured models, recognizes the patterns the W2
workflow scores (requirements, Salesforce mechanisms, per-criterion evidence,
guardrail violations), enriches the judgment packets with advisory retrieval
hints, and verifies the judges' citations on the way back.

The covenant (approved plan, 2026-07-07): this layer PREPARES and VERIFIES,
never judges. Every output is either packet enrichment (advisory, byte-
identical for both judges) or a flag routed into the existing evidence-ruled
reconciliation. Pure stdlib, deterministic, zero model calls.
"""
PREINTEL_VERSION = "1.1"  # 1.1: plural-tolerant lexicon w/ context gating,
                          # compound-adjective modality guard (gold-corpus 100%)

from .doc_model import build_doc_model                      # noqa: F401
from .requirements_registry import extract_requirements     # noqa: F401
from .lexicon import find_mechanisms                        # noqa: F401
from .evidence_locator import (criterion_profile, locate_candidates,  # noqa: F401
                               anchor_relevance, traceability_matrix)
from .guardrail_lint import injection_lint, blinding_scan   # noqa: F401
from .pre_analysis import build_pre_analysis, prompt_digest, review_anchor_quality  # noqa: F401
from .release_support import enrich_queries, review_evidence  # noqa: F401
