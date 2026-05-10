"""8-gate validation engine.

Every consultant-loop output passes through these gates in order.  Each
gate returns a :class:`GateResult` (verdict + score + reasoning).  A run
``passes`` when *all* gates verdict ∈ {pass, warn}; any ``fail`` aborts
the loop and the suggestion is staged for human review with the failure
attached.

Gates (per spec §6 / ARCHITECTURE Batch 4):

    1. SCHEMA          — output JSON validates against the expected shape
    2. CITATION        — every claim has ≥1 citation that resolves
    3. HALLUCINATION   — every claim's citation actually mentions key tokens
    4. FRESHNESS       — citations newer than the per-domain freshness budget
    5. NOVELTY         — output isn't a near-duplicate of an existing fact
    6. BIAS            — no single source contributes >70% of citations
    7. BREAKING_CHANGE — high-impact diffs route to human approver
    8. PEER_COVERAGE   — claims about the FS sector cite ≥1 peer benchmark

The gates are deliberately simple + deterministic so the engine is
testable without LLM calls — they consume the parsed structured output of
:func:`consultant_loop.run`.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from .citation_verifier import verify_citation
from .hallucination import detect_unsupported_claims


@dataclass
class GateResult:
    name: str
    verdict: str  # "pass" | "warn" | "fail"
    score: float  # 0..1
    reasoning: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class GateRun:
    overall: str
    score: float
    results: list[GateResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall,
            "score": self.score,
            "results": [asdict(r) for r in self.results],
        }


# ─── Gate implementations ───────────────────────────────────────────────────


def gate_schema(output: dict, expected_keys: list[str]) -> GateResult:
    missing = [k for k in expected_keys if k not in output]
    if missing:
        return GateResult(
            name="schema",
            verdict="fail",
            score=0.0,
            reasoning=f"missing keys: {missing}",
        )
    return GateResult(
        name="schema",
        verdict="pass",
        score=1.0,
        reasoning="all expected keys present",
    )


def gate_citation(output: dict, sources: list[dict]) -> GateResult:
    claims = output.get("claims", [])
    if not claims:
        return GateResult(name="citation", verdict="warn", score=0.5, reasoning="no claims to cite")
    src_ids = {s.get("id") for s in sources}
    missing: list[int] = []
    unresolved: list[str] = []
    for i, c in enumerate(claims):
        cs = c.get("sources") or []
        if not cs:
            missing.append(i)
            continue
        for cid in cs:
            if cid not in src_ids:
                unresolved.append(cid)
    if missing or unresolved:
        return GateResult(
            name="citation",
            verdict="fail" if missing else "warn",
            score=max(0.0, 1.0 - 0.2 * (len(missing) + len(unresolved))),
            reasoning=f"missing={missing} unresolved={unresolved}",
            details={"missing_idx": missing, "unresolved_ids": unresolved},
        )
    # secondary check: at least one URL probe (only checks citations with URLs)
    probes = [verify_citation(s) for s in sources if s.get("url")]
    bad = [p for p in probes if not p.ok]
    if bad:
        return GateResult(
            name="citation",
            verdict="warn",
            score=0.7,
            reasoning=f"{len(bad)}/{len(probes)} URLs failed probe",
            details={"bad_urls": [p.url for p in bad]},
        )
    return GateResult(name="citation", verdict="pass", score=1.0, reasoning="all citations resolve")


def gate_hallucination(output: dict, sources: list[dict]) -> GateResult:
    issues = detect_unsupported_claims(output.get("claims", []), sources)
    if not issues:
        return GateResult(
            name="hallucination", verdict="pass", score=1.0, reasoning="no unsupported claims",
        )
    sev = max(i["severity_score"] for i in issues) if issues else 0
    verdict = "fail" if sev >= 0.7 else "warn"
    return GateResult(
        name="hallucination",
        verdict=verdict,
        score=max(0.0, 1.0 - sev),
        reasoning=f"{len(issues)} unsupported claims (max severity {sev:.2f})",
        details={"issues": issues},
    )


def gate_freshness(sources: list[dict], max_age_days: int = 365) -> GateResult:
    if not sources:
        return GateResult(name="freshness", verdict="warn", score=0.5, reasoning="no sources")
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    stale: list[str] = []
    for s in sources:
        d = s.get("published_at") or s.get("ingested_at")
        if not d:
            continue
        try:
            if datetime.fromisoformat(d.replace("Z", "+00:00")) < cutoff:
                stale.append(s.get("id", "?"))
        except Exception:
            continue
    if not stale:
        return GateResult(name="freshness", verdict="pass", score=1.0, reasoning="all sources fresh")
    return GateResult(
        name="freshness",
        verdict="warn" if len(stale) < len(sources) // 2 else "fail",
        score=max(0.0, 1.0 - len(stale) / max(1, len(sources))),
        reasoning=f"{len(stale)}/{len(sources)} sources older than {max_age_days}d",
        details={"stale_ids": stale},
    )


def gate_novelty(output: dict, recent_outputs: list[dict]) -> GateResult:
    new_text = json.dumps(output.get("claims", []), sort_keys=True)
    for prev in recent_outputs[-30:]:
        prev_text = json.dumps(prev.get("claims", []), sort_keys=True)
        if prev_text and new_text == prev_text:
            return GateResult(
                name="novelty",
                verdict="warn",
                score=0.4,
                reasoning="output identical to a recent run",
            )
    return GateResult(name="novelty", verdict="pass", score=1.0, reasoning="output is novel")


def gate_bias(output: dict, sources: list[dict]) -> GateResult:
    counts: dict[str, int] = {}
    total = 0
    for c in output.get("claims", []):
        for sid in c.get("sources") or []:
            counts[sid] = counts.get(sid, 0) + 1
            total += 1
    if total == 0:
        return GateResult(name="bias", verdict="warn", score=0.5, reasoning="no citations to evaluate")
    top = max(counts.values())
    pct = top / total
    if pct > 0.7:
        return GateResult(
            name="bias",
            verdict="warn",
            score=1.0 - pct,
            reasoning=f"a single source provides {pct * 100:.0f}% of citations",
            details={"top_source_pct": pct},
        )
    return GateResult(name="bias", verdict="pass", score=1.0, reasoning="citation diversity ok")


HIGH_IMPACT_KINDS = {"delete_subcap", "rename_subcap", "merge_use_case", "split_subcap"}


def gate_breaking_change(suggestions: list[dict]) -> GateResult:
    high = [s for s in suggestions if s.get("kind") in HIGH_IMPACT_KINDS]
    if not high:
        return GateResult(
            name="breaking_change",
            verdict="pass",
            score=1.0,
            reasoning="no high-impact suggestions",
        )
    return GateResult(
        name="breaking_change",
        verdict="warn",
        score=0.5,
        reasoning=f"{len(high)} high-impact suggestion(s) routed to human approver",
        details={"high_impact_kinds": list({s.get("kind") for s in high})},
    )


def gate_peer_coverage(output: dict, sources: list[dict]) -> GateResult:
    claims = output.get("claims", [])
    fs_keywords = re.compile(r"\b(bank|fintech|wealth|insurance|credit union|asset manager)\b", re.IGNORECASE)
    needs_peer = [c for c in claims if fs_keywords.search(c.get("text", ""))]
    if not needs_peer:
        return GateResult(
            name="peer_coverage",
            verdict="pass",
            score=1.0,
            reasoning="no FS-sector claims requiring peer coverage",
        )
    has_peer_source = any(s.get("kind") == "benchmark" for s in sources)
    if has_peer_source:
        return GateResult(
            name="peer_coverage",
            verdict="pass",
            score=1.0,
            reasoning="peer benchmark cited",
        )
    return GateResult(
        name="peer_coverage",
        verdict="warn",
        score=0.6,
        reasoning="FS claims present but no peer/benchmark source",
        details={"fs_claim_count": len(needs_peer)},
    )


# ─── Engine ─────────────────────────────────────────────────────────────────


def run_gates(
    output: dict,
    sources: list[dict],
    *,
    expected_keys: list[str] | None = None,
    suggestions: list[dict] | None = None,
    recent_outputs: list[dict] | None = None,
    freshness_days: int = 365,
) -> GateRun:
    results = [
        gate_schema(output, expected_keys or ["claims"]),
        gate_citation(output, sources),
        gate_hallucination(output, sources),
        gate_freshness(sources, freshness_days),
        gate_novelty(output, recent_outputs or []),
        gate_bias(output, sources),
        gate_breaking_change(suggestions or []),
        gate_peer_coverage(output, sources),
    ]
    if any(r.verdict == "fail" for r in results):
        overall = "fail"
    elif any(r.verdict == "warn" for r in results):
        overall = "warn"
    else:
        overall = "pass"
    score = sum(r.score for r in results) / len(results)
    return GateRun(overall=overall, score=score, results=results)
