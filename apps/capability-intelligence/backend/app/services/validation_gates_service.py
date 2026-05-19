"""8-gate validation engine — spec G1..G8 + auxiliary checks.

Per QA_AUDIT.md fix #1: the spec calls for these eight gates (named
G1..G8) and our previous gate set was off-spec. We now ship the spec
parity AND keep the previous gates as ``aux_*`` because they catch
real defects (hallucination, freshness, peer coverage, bias, breaking
change, schema, citation).

Spec-parity gates (per spec §5):

    G1 NOVELTY         — output is semantically new (not duplicate of recent runs)
    G2 SOURCE_QUALITY  — ≥1 T1 OR ≥2 T2 sources
    G3 ERS             — Evidence Relevance Score ≥ threshold
                         (weights 0.35 recency / 0.25 tier / 0.20 independence
                          / 0.20 specificity, calibrated against golden_ers.json)
    G4 INDEPENDENCE    — ≥2 distinct publisher organisations after dedup by
                         :func:`source_org_id` (closes QA_AUDIT F07: previously
                         deduped on URL-hashed primary_source_id, which let two
                         articles from the same publisher count as independent)
    G5 CONSISTENCY     — no internal contradiction across claims (token-overlap heuristic)
    G6 ADVERSARIAL     — adversarial reviewer verdict ≤ MEDIUM severity;
                         marks `degraded=true` when Anthropic Sonnet is unavailable
    G7 DRIFT           — output within 2σ of recent historical output distribution;
                         `warming_up` while history < 50 runs
    G8 ABSENCE         — when claim asserts no-evidence, ≥k T1/T2 negative-search hits

Auxiliary gates (kept for defect-coverage, but reported under `aux`):

    aux_schema, aux_citation, aux_hallucination, aux_freshness,
    aux_bias, aux_breaking_change, aux_peer_coverage

The gate run as a whole ``passes`` when no gate verdict is ``fail``;
``warn`` is allowed. G6 + G8 + aux_breaking_change have specific
remediation rules documented per QA_AUDIT §2.3.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from .citation_verifier import verify_citation
from .hallucination import detect_unsupported_claims

# ─── F07 fix — canonical source-org identifier for triangulation ─────────────
#
# Two URLs from the same publisher (occ.gov/news/x and occ.gov/blog/y)
# must collapse to a single independent source. The previous dedup keyed
# on ``primary_source_id`` OR ``id`` — both URL-derived — which let two
# pages from the same regulator count as two independent sources. This
# helper returns a canonical organisation identifier so dedup is keyed on
# the publisher, not the page.

# Registrable-domain shortcuts for the publishers we ingest most often.
# Avoids importing a heavyweight PSL library; the catalogue's source list
# is finite and stable enough to hand-curate.
_PUBLIC_SUFFIXES = (
    "co.uk", "ac.uk", "gov.uk", "org.uk", "com.au", "co.nz", "co.jp",
)


def _registrable_domain(host: str) -> str:
    """Best-effort registrable-domain extraction.

    Strips a single subdomain layer (``www.occ.gov`` → ``occ.gov``);
    preserves the two-label public suffixes we encounter
    (``foo.example.co.uk`` → ``example.co.uk``).
    """
    host = (host or "").lower().strip(".")
    if not host or ":" in host or all(c.isdigit() or c == "." for c in host):
        return host
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    last_two = ".".join(labels[-2:])
    if last_two in _PUBLIC_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def source_org_id(source: dict) -> str:
    """Return the canonical publisher identifier for a source row.

    Resolution order:
    1. ``source_org_id`` — explicit override the ingest layer can set.
    2. ``source_id`` — matches the ``canonical_sources_policy.yml``
       registry key (e.g. ``occ``, ``fdic``).
    3. The registrable domain of the source's URL.
    4. ``source`` field (already a domain string on news rows).
    5. ``primary_source_id`` / ``id`` — last-resort fallback so a row
       without a publisher is still dedup-keyed by itself, not collapsed
       with every other anonymous row.
    """
    if not isinstance(source, dict):
        return ""
    explicit = source.get("source_org_id")
    if explicit:
        return str(explicit).lower().strip()
    sid = source.get("source_id")
    if sid:
        return str(sid).lower().strip()
    url = source.get("url") or source.get("source_url")
    if url:
        try:
            host = urlparse(str(url)).hostname or ""
        except Exception:
            host = ""
        dom = _registrable_domain(host)
        if dom:
            return dom
    src = source.get("source")
    if src and "." in str(src):
        return _registrable_domain(str(src))
    return str(
        source.get("primary_source_id")
        or source.get("id")
        or ""
    ).lower().strip()


def distinct_source_orgs(sources: list[dict]) -> set[str]:
    """Helper exported for the gates + consultant-loop dedup paths."""
    return {source_org_id(s) for s in (sources or []) if source_org_id(s)}


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


# ─── Spec-parity gates G1..G8 ───────────────────────────────────────────────


def gate_g1_novelty(output: dict, recent_outputs: list[dict]) -> GateResult:
    """G1 — output is semantically new vs. recent runs."""
    new_text = json.dumps(output.get("claims", []), sort_keys=True)
    for prev in recent_outputs[-50:]:
        if json.dumps(prev.get("claims", []), sort_keys=True) == new_text:
            return GateResult(
                name="g1_novelty",
                verdict="warn",
                score=0.4,
                reasoning="output identical to a recent run",
            )
    return GateResult(name="g1_novelty", verdict="pass", score=1.0,
                      reasoning="output is novel")


def gate_g2_source_quality(output: dict, sources: list[dict]) -> GateResult:
    """G2 — ≥1 T1 OR ≥2 T2 sources required."""
    from collections import Counter
    tiers: Counter[str] = Counter(s.get("tier") for s in sources if s.get("tier"))
    if tiers.get("T1", 0) >= 1 or tiers.get("T2", 0) >= 2:
        return GateResult(
            name="g2_source_quality", verdict="pass", score=1.0,
            reasoning=f"tier mix passes minima (T1={tiers.get('T1', 0)}, T2={tiers.get('T2', 0)})",
            details={"tier_counts": dict(tiers)},
        )
    return GateResult(
        name="g2_source_quality", verdict="fail", score=0.0,
        reasoning=f"need ≥1 T1 or ≥2 T2; got {dict(tiers)}",
        details={"tier_counts": dict(tiers),
                 "remediation": "downgrade claim_label → HYPOTHESIS"},
    )


def _ers_components(output: dict, sources: list[dict]) -> dict[str, float]:
    """ERS sub-components scored ∈ [0,1]:
        recency      = fraction of sources newer than freshness window
        tier         = mean tier rank where T1=1.0, T2=0.75, T3=0.5, T4=0.25, T5=0.1
        independence = unique primary sources / total sources
        specificity  = fraction of claims that name a specific subcap_id
    """
    if not sources:
        return {"recency": 0.0, "tier": 0.0, "independence": 0.0, "specificity": 0.0}
    rec_cutoff = datetime.now(timezone.utc) - timedelta(days=365)
    fresh = 0
    for s in sources:
        ts = s.get("published_at") or s.get("ingested_at")
        try:
            if ts and datetime.fromisoformat(ts.replace("Z", "+00:00")) >= rec_cutoff:
                fresh += 1
        except Exception:
            continue
    tier_rank = {"T1": 1.0, "T2": 0.75, "T3": 0.5, "T4": 0.25, "T5": 0.1}
    tier_score = sum(tier_rank.get(s.get("tier", ""), 0.0) for s in sources) / len(sources)
    # F07 fix — dedup on the publisher organisation, not URL-derived ids,
    # so two articles from the same regulator don't double-count as
    # independent sources.
    orgs = distinct_source_orgs(sources)
    independence = (len(orgs) / len(sources)) if sources else 0.0
    claims = output.get("claims", []) or []
    if claims:
        specificity = sum(1 for c in claims if c.get("subcap_id")) / len(claims)
    else:
        specificity = 0.0
    return {
        "recency": fresh / len(sources),
        "tier": tier_score,
        "independence": independence,
        "specificity": specificity,
    }


def gate_g3_ers(
    output: dict, sources: list[dict], *, threshold: float = 0.55,
) -> GateResult:
    """G3 — weighted ERS ≥ threshold (weights from spec §5)."""
    weights = {"recency": 0.35, "tier": 0.25, "independence": 0.20, "specificity": 0.20}
    components = _ers_components(output, sources)
    ers = sum(weights[k] * components[k] for k in weights)
    return GateResult(
        name="g3_ers",
        verdict="pass" if ers >= threshold else "warn",
        score=round(ers, 3),
        reasoning=f"ERS={ers:.2f} (threshold {threshold:.2f}); components={ {k: round(v,2) for k,v in components.items()} }",
        details={"components": components, "threshold": threshold,
                 "weights": weights,
                 "remediation": "downgrade ERS-derived confidence; do not block"},
    )


def gate_g4_independence(output: dict, sources: list[dict]) -> GateResult:
    """G4 — ≥2 distinct *publisher organisations* required after dedup.

    F07 fix: prior to this rev the gate deduped on
    ``primary_source_id`` (typically a URL hash), which let two articles
    from the same publisher (``occ.gov/news/x`` + ``occ.gov/blog/y``)
    pass triangulation. Now dedup uses :func:`source_org_id`, which
    collapses every URL from the same registrable domain or registry
    key into a single bucket.
    """
    if not sources:
        return GateResult(name="g4_independence", verdict="warn", score=0.5,
                          reasoning="no sources to evaluate")
    orgs = distinct_source_orgs(sources)
    if len(orgs) >= 2:
        return GateResult(name="g4_independence", verdict="pass", score=1.0,
                          reasoning=f"{len(orgs)} distinct publisher org(s)",
                          details={"orgs": sorted(orgs)})
    return GateResult(
        name="g4_independence", verdict="fail", score=0.0,
        reasoning=f"only {len(orgs)} distinct publisher org(s); triangulation requires ≥2",
        details={"orgs": sorted(orgs),
                 "remediation": "mark as `single_source_evidence`; require human confirm"},
    )


_NEG_TOKENS = {"not", "no", "without", "lacks", "absent", "fails to"}


def gate_g5_consistency(output: dict) -> GateResult:
    """G5 — no internal contradiction across claims (heuristic).

    Flags if any pair of claims share ≥2 salient tokens but one negates
    the other. Cheap rule-based; LLM tiebreak in live mode.
    """
    import re

    claims = output.get("claims", []) or []
    if len(claims) < 2:
        return GateResult(name="g5_consistency", verdict="pass", score=1.0,
                          reasoning="<2 claims to compare")
    word_re = re.compile(r"[A-Za-z]{4,}")

    def tokens(t: str) -> set[str]:
        return {w.lower() for w in word_re.findall(t or "")}

    def is_negated(t: str) -> bool:
        return any(n in (t or "").lower().split() for n in _NEG_TOKENS)

    contradictions: list[tuple[int, int]] = []
    for i, a in enumerate(claims):
        a_t = tokens(a.get("text", ""))
        for j in range(i + 1, len(claims)):
            b = claims[j]
            b_t = tokens(b.get("text", ""))
            if len(a_t & b_t) >= 2 and is_negated(a.get("text", "")) != is_negated(b.get("text", "")):
                contradictions.append((i, j))
    if not contradictions:
        return GateResult(name="g5_consistency", verdict="pass", score=1.0,
                          reasoning=f"{len(claims)} claims; no contradictions")
    return GateResult(
        name="g5_consistency", verdict="warn", score=max(0.2, 1.0 - 0.1 * len(contradictions)),
        reasoning=f"{len(contradictions)} potentially contradictory claim pair(s)",
        details={"pairs": contradictions,
                 "remediation": "enter contradiction-resolution flow"},
    )


def gate_g6_adversarial(adversarial: dict | None, *, anthropic_degraded: bool = False) -> GateResult:
    """G6 — adversarial reviewer verdict ≤ MEDIUM severity.

    The adversarial review is produced by ``consultant_loop._adversarial``.
    We surface its verdict + max issue severity here.
    """
    if not adversarial:
        return GateResult(name="g6_adversarial", verdict="warn", score=0.5,
                          reasoning="no adversarial review attached")
    verdict_label = (adversarial.get("verdict") or "").lower()
    score_val = float(adversarial.get("score") or 0.5)
    severities = [
        (i.get("severity") or "").upper()
        for i in adversarial.get("issues") or []
    ]
    sev_rank = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4, "BLOCKING": 5}
    max_sev = max((sev_rank.get(s, 0) for s in severities), default=0)
    if max_sev >= sev_rank["HIGH"]:
        return GateResult(
            name="g6_adversarial", verdict="fail", score=score_val,
            reasoning=f"adversarial flagged HIGH+ severity (verdict={verdict_label})",
            details={"max_severity": max_sev, "anthropic_degraded": anthropic_degraded,
                     "remediation": "block; or hold + re-run when Anthropic recovers" if anthropic_degraded else "block"},
        )
    if anthropic_degraded:
        return GateResult(
            name="g6_adversarial", verdict="warn", score=score_val,
            reasoning="adversarial passed but Anthropic degraded → Pro-on-Pro risk",
            details={"degraded": True,
                     "remediation": "hold; re-run when Sonnet available before BENCHMARK promotion"},
        )
    return GateResult(name="g6_adversarial", verdict="pass", score=score_val,
                      reasoning=f"adversarial verdict={verdict_label}, max_sev={max_sev}")


def gate_g7_drift(
    output: dict,
    *,
    history: list[dict] | None = None,
    min_history: int = 50,
) -> GateResult:
    """G7 — current output's score within 2σ of historical mean.

    Boots in `warming_up` mode while we have <`min_history` rows.
    """
    import statistics

    hist = history or []
    if len(hist) < min_history:
        return GateResult(
            name="g7_drift", verdict="warn", score=0.5,
            reasoning=f"warming_up: history={len(hist)} (<{min_history})",
            details={"warming_up": True},
        )
    scores = [float(h.get("ers") or 0.0) for h in hist if h.get("ers") is not None]
    if not scores:
        return GateResult(name="g7_drift", verdict="warn", score=0.5,
                          reasoning="no historical ERS values")
    mean = statistics.mean(scores)
    std = statistics.pstdev(scores) or 0.01
    cur = float(output.get("ers") or mean)
    z = abs((cur - mean) / std)
    if z > 2:
        return GateResult(
            name="g7_drift", verdict="warn", score=max(0.0, 1.0 - z * 0.1),
            reasoning=f"|z|={z:.2f} > 2σ from mean {mean:.2f}",
            details={"z": z, "mean": mean, "std": std,
                     "remediation": "banner: drift detected; do not block"},
        )
    return GateResult(name="g7_drift", verdict="pass", score=1.0,
                      reasoning=f"|z|={z:.2f} within 2σ", details={"z": z})


def gate_g8_absence(
    output: dict,
    sources: list[dict],
    *,
    k: int = 5,
) -> GateResult:
    """G8 — when output asserts no-evidence, demand ≥k T1/T2 negative searches."""
    asserts_absence = any(
        "no evidence" in (c.get("text") or "").lower()
        or "absence" in (c.get("text") or "").lower()
        for c in output.get("claims", []) or []
    )
    if not asserts_absence:
        return GateResult(name="g8_absence", verdict="pass", score=1.0,
                          reasoning="no absence claim — gate not applicable")
    high_tier = [s for s in sources if s.get("tier") in ("T1", "T2")]
    if len(high_tier) >= k:
        return GateResult(
            name="g8_absence", verdict="pass", score=1.0,
            reasoning=f"absence proven across {len(high_tier)} T1/T2 sources",
        )
    return GateResult(
        name="g8_absence", verdict="warn", score=max(0.0, len(high_tier) / k),
        reasoning=f"absence claimed but only {len(high_tier)}/{k} T1/T2 negative searches",
        details={"remediation": "allow with claim_label=CEILING_ESTIMATE + explicit absence note"},
    )


# ─── Engine — replaces previous run_gates ──────────────────────────────────


def run_gates(
    output: dict,
    sources: list[dict],
    *,
    expected_keys: list[str] | None = None,
    suggestions: list[dict] | None = None,
    recent_outputs: list[dict] | None = None,
    freshness_days: int = 365,
    adversarial: dict | None = None,
    anthropic_degraded: bool = False,
    history: list[dict] | None = None,
) -> GateRun:
    """Run spec G1..G8 + auxiliary gates; aggregate to overall verdict.

    Result dict contains:
        results: list of all gate rows (G1..G8 + aux_*)
        overall: pass | warn | fail
        score: arithmetic mean of per-gate scores
    """
    spec_gates = [
        gate_g1_novelty(output, recent_outputs or []),
        gate_g2_source_quality(output, sources),
        gate_g3_ers(output, sources),
        gate_g4_independence(output, sources),
        gate_g5_consistency(output),
        gate_g6_adversarial(adversarial, anthropic_degraded=anthropic_degraded),
        gate_g7_drift(output, history=history),
        gate_g8_absence(output, sources),
    ]
    aux_gates = [
        _aux(gate_schema, "aux_schema", output, expected_keys or ["claims"]),
        _aux(gate_citation, "aux_citation", output, sources),
        _aux(gate_hallucination, "aux_hallucination", output, sources),
        _aux(gate_freshness, "aux_freshness", sources, freshness_days),
        _aux(gate_bias, "aux_bias", output, sources),
        _aux(gate_breaking_change, "aux_breaking_change", suggestions or []),
        _aux(gate_peer_coverage, "aux_peer_coverage", output, sources),
    ]
    results = spec_gates + aux_gates
    if any(r.verdict == "fail" for r in results):
        overall = "fail"
    elif any(r.verdict == "warn" for r in results):
        overall = "warn"
    else:
        overall = "pass"
    score = sum(r.score for r in results) / len(results)
    return GateRun(overall=overall, score=score, results=results)


def _aux(fn, name: str, *args, **kwargs) -> GateResult:
    """Run an existing legacy gate and rename it under aux_*."""
    r = fn(*args, **kwargs)
    return GateResult(
        name=name, verdict=r.verdict, score=r.score,
        reasoning=r.reasoning, details=r.details,
    )
