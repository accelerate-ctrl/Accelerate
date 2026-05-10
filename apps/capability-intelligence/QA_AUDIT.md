# Capability Intelligence Agent — Adversarial QA Audit

**Auditor**: principal engineer + FS consulting methodology + cost engineering
**Audit branch**: `claude/deploy-zennify-cloud-run-AUdu6` @ `d1c03e9`
**Scope**: v3 spec §1-§24 vs implementation in `apps/capability-intelligence/` (Batches 0-9)
**Method**: code-grounded, evidence-anchored, adversarial. Every finding has section ref + file:line + verdict + concrete fix + measurable AC + priority.

> **Headline.** The implementation ships the *control flow* of the spec (28 routes, 14 jobs, 7-step loop, 8 gates, KG with 4014/12249 nodes/edges) but is missing five **P0 blocking** structural pieces required by the v3 spec: claim-label/ERS plumbing on every claim emission, schema-versioned Firestore docs, embedded self-test on every component output, golden datasets, and the pre-trained capability cluster + cross-pillar integration module. **Eleven P0** items must land before this can be sold as "industry-grade." None of them are large; total fix effort is ~14 engineer-days end-to-end.

---

## §1. Spec Compliance Matrix (§1–§24)

| §   | Topic                                        | Status        | Evidence                                                                                                                                       |
|-----|----------------------------------------------|---------------|------------------------------------------------------------------------------------------------------------------------------------------------|
| §1  | Mandate / canonical schema                   | **Partial**   | Pillar 1 ingests cleanly; ingest is data-driven (`sheets_parser.py`); but no synthetic-P2 acceptance test exists yet. Defect: parameterization not proven. |
| §2  | Personas (5)                                 | Compliant     | `personas_service.py` indexes 102 personas from `subcaps.personas`.                                                                            |
| §3  | Cost discipline / model routing              | **Partial**   | Router + cache + tracker live (`services/llm/`). Token math not yet reconciled — **see §2.1 below**. No per-(operation, pillar, subvertical) attribution. |
| §4  | 7-step consulting loop                       | **Partial**   | Loop ships (`consultant_loop.py`) but step 4 has **no primary-source dedup**, step 5 contradiction rules don't include "later contradicts earlier," and there's no leverage-tier policy (every op runs full loop = unsustainable). |
| §5  | 8 validation gates                           | **Defect**    | Implemented gates (`schema, citation, hallucination, freshness, novelty, bias, breaking_change, peer_coverage`) **don't match spec G1–G8** (semantic-novelty, source-quality, ERS≥threshold, independence, consistency, adversarial, drift, absence). Naming + semantics drift. **P0 BLOCKING.** |
| §6  | Canonical sources                            | **Partial**   | `config/canonical_sources.yml` has 50+ sources with `tier`, `polling_interval_minutes`. Missing: `independence_class`, `max_requests_per_minute`, `backoff_policy`, ToS-acceptance flag, JS-render fallback. |
| §7  | Capability map + 15 drilldowns               | **Partial**   | Capability Explorer + Subcap Deep Dive ship; sunburst renders. Reverse drilldown (D2) implicit; not all 15 patterns tested. URL-state schema undocumented. |
| §8  | Knowledge Graph (28 node, 50+ edge types)    | **Partial**   | KG ships with **14 node types / 13 edge types** vs spec's **28 / 50+**. Missing: Vendor, Event, Benchmark, Suggestion, ReasoningChain, Audit, Persona-Subvertical, Story-Subcap edges, claim_state on edges, `SEMANTICALLY_SIMILAR` cosine edge. **P0 partial.** |
| §9  | Project structure                            | **Partial**   | 30 routers + 32 services + 14 jobs land. Missing: `import-linter` enforcement, `mypy --strict`, dependency-injection framework. |
| §10 | KG storage                                   | **Defect**    | Spec wants `subcaps_graph/{snapshot_id}` Firestore docs; we cache NetworkX in-process. Migrate to sharded persistence (per pillar). 1 MB Firestore doc limit will bite at production scale. |
| §11 | Per-feature delivery (subsections)           | **Mixed**     | See §11.x rows below.                                                                                                                          |
| §11.6 | Benchmarks engine                          | **Partial**   | Filings + analyst + technographics ingest live; verdict math live. Missing: hierarchical bootstrap CI, dimensional validator on numeric extraction, primary-source dedup before triangulation. |
| §11.7 | Quarterly digest                           | **Partial**   | Digest ships; PPTX export valid. Opus daily-budget arithmetic **fails** under the spec's stated budget — **see §2.8**. No checkpointed multi-day execution. |
| §11.8 | Lifecycle engine                           | **Partial**   | Live. Weights uncalibrated; no upstream-confidence pipe-through. |
| §11.12 | What-if simulator                         | **Compliant** | Pure-function read-only simulator. Concurrency semantics undocumented (single-user assumed). Per-user cost cap missing. |
| §11.15 | Hallucination + citation verifier         | **Partial**   | Salient-token rule + URL HEAD probe live. No labelled calibration set; precision/recall not measured. |
| §12 | Reasoning Chain Viewer                       | Compliant     | Page renders 7 steps + claims + sources + 8 gates with chain links.                                                                            |
| §13 | Sidebar / 28-page nav                        | Compliant     | 29 pages routed; sidebar groups present (`Sidebar.tsx`).                                                                                       |
| §14 | Brand                                        | Compliant     | 8-token palette in `tailwind.config.ts`; mirrored in `pptx_export.py` + `exports_service.py` after the post-Batch-9 reconciliation (commit `d1c03e9`). Icon teal `#27BBAF`. |
| §15 | Personas + persona switcher                  | **Partial**   | Persona views live; persona-aware UI vocabulary swap not implemented (one CIO ≠ one Frontline-banker UI today). |
| §16 | Notifications                                | Compliant     | Feed with severity + read-flag; bell icon TBD (not in scope). Email channel not wired (Slack/PD pending creds). |
| §17 | Observability                                | **Defect**    | OTel install ships; **no SLOs documented**, no error-budget binding to deploys, no per-job trace-context propagation guarantee. |
| §18 | Reliability / DR                             | **Partial**   | RUNBOOK §8 documents 4h RTO / 24h RPO. Firestore PITR not enabled. DR drill cadence not specified as quarterly. |
| §19 | Testing                                      | **Partial**   | 319 pytest + 45 vitest pass. **No golden datasets** committed. No property-based tests (`hypothesis`). No mutation testing (`mutmut`). |
| §20 | Cloud-Run jobs / scheduler / Pub/Sub         | Compliant     | 14 jobs + 14 cron entries + 5 topics + DLQ + Terraform module.                                                                                  |
| §21 | Drive watcher / version-on-save              | Compliant     | Drive ingest auto-discovery; version snapshots on save (Batch 1).                                                                              |
| §22 | Acceptance criteria (40)                     | **Defect**    | Most ACs are "X works" not measurable. **No SLOs, no error budgets, no security ACs.** Replace per §9 below. |
| §23 | Roadmap                                      | Compliant     | 10 batches in README marked shipped.                                                                                                          |
| §24 | ADRs                                         | **Partial**   | ADR-0001..0006 exist in ARCHITECTURE.md. Missing ADR-0007 (DocAI custom infoTypes), 0008 (leverage tiers), 0009 (multi-sample policy), 0010 (hierarchical bootstrap), 0011 (Opus budget vs digest scope). |

**Compliance score**: 7 Compliant / 13 Partial / **4 Defect / Blocking** out of 24.

---

## §2. Adversarial Findings Register

> Verdict + evidence + fix + AC + priority. Skipping any "noted" answers; every fix is concrete.

### 2.1 Cost discipline & model routing — token-budget feasibility

**Math (under spec's stated load + budgets):**

| Workload                              | Calls/day            | In tok/call | Out tok/call | In/day      | Out/day    | Daily budget       | Verdict      |
|---------------------------------------|----------------------|-------------|--------------|-------------|------------|--------------------|--------------|
| News poll, 7-step loop on FS-relevant | 100                  | 8 K         | 1 K          | 800 K       | 100 K      | Pro: 50 M / 5 M    | OK (1.6% / 2%) |
| Lifecycle scoring nightly (199 subcaps) | 1                  | 12 K        | 1.5 K        | 12 K        | 1.5 K      | Flash: 500 M / 50 M | trivial       |
| Suggestion generation (10/day)        | 10                   | 15 K        | 2 K          | 150 K       | 20 K       | Sonnet: 3 M / 500 K| 5% / 4%      |
| **Quarterly digest (10 subverticals × 5 priorities × 7-step loop)** | 50 (one day) | 30 K | 5 K | 1.5 M | **250 K**     | Opus: 300 K / **60 K** | **FAIL: 833% / 417%** |
| Deep audit weekly                     | 1 (full catalog)     | 200 K       | 10 K         | 200 K       | 10 K       | Opus daily         | **17% / 17% — fits but eats other Opus work** |

**Verdict — defect (P0).** The Opus daily output budget (60 K/day) cannot accommodate a single-day full digest run. Three options; pick one and document.

**Fix (one of):**
1. **Multi-day checkpointed digest** — run 1 subvertical/day × 10 days; persist `digest_runs/{run_id}` with `state=in_progress` and resume; emit final digest only when 10/10 complete.
2. **Downgrade per-subvertical synthesis to Sonnet** (cheaper, 8M/day in / 1M out) and reserve Opus only for the executive summary + cross-pillar coherence (≤ 20K out total).
3. **Raise the Opus budget** by negotiated quota with Anthropic.

**AC**: digest never exceeds Opus 60 K out/day in any UTC day; if the run would exceed, it pauses and emits `digest_run.checkpoint` event; resume succeeds.

**Cache target ≥ 40% — refute.** Cacheable content classes (calibrate independently, not as one global):
- Embeddings: ≥ 95% (idempotent)
- News categorisation by URL hash dedup: ≥ 60%
- Similarity searches with stable corpus: ≥ 70%
- LLM reasoning over unique evidence packs: **≤ 5%** (each consultant loop is a unique prompt)

**Fix**: replace global 40% target in `COST_GUIDE.md` with per-class targets above; add a `cache_class` label to `llm_cache` rows; alert per class.

**Auto-degrade preserves G6?** No. When Anthropic 90% budget hits and Sonnet adversary degrades to Pro, the dialectic collapses to Pro-on-Pro. Mark gate `G6` with `degraded=true` and deny `BENCHMARK` verdict on any benchmark whose adversary ran in degraded mode.

**Per-tenant attribution.** Every LLM call must log `(operation_type, pillar, subvertical, subcap_id?, batch?)`. Today only `model + tokens + cost` log. **P1**.

```python
# backend/app/services/llm/cost_tracker.py — patch
def record(self, model: ModelKind, input_tokens: int, output_tokens: int,
           cost_usd: float, *, operation_type: str, pillar_id: str | None = None,
           subvertical: str | None = None, sub_cap_id: str | None = None) -> None: ...
```

### 2.2 Consulting reasoning loop

**Per-suggestion cost (today's loop).** Synthesize (Pro 8K in / 1K out = $0.030) + adversarial (Sonnet 4K in / 0.5K out = $0.027) + propose (Sonnet 4K in / 0.5K out = $0.027) ≈ **$0.084/suggestion** in live mode. 100 suggestions/day = $8.4/day = **$252/month** for suggestions alone — within reason; spec's $0.40 estimate was 5× pessimistic.

**Skip-the-loop policy — defect.** `consultant_loop.run` always runs all 8 logged steps (`clarify, retrieve_internal, retrieve_external, synthesize, adversarial, propose_suggestions, gate, finalize`). Spec's "no operation skips steps" is uneconomical for trivial classification.

**Fix**: add a `LeverageTier` enum + per-call dispatch.
```python
class LeverageTier(str, Enum):
    LOW    = "low"      # synthesize + gate only (no adversarial / no propose)
    MEDIUM = "medium"   # synthesize + adversarial + gate
    HIGH   = "high"     # full 8-step (current default)
    DIGEST = "digest"   # full + cross-pillar coherence + Opus

def run(*, query, sub_cap_id=None, synth_model=ModelKind.GEMINI_PRO,
        leverage_tier: LeverageTier = LeverageTier.HIGH, persist: bool = True): ...
```
**AC**: `lifecycle_scoring_daily` runs with `LOW`, costs ≤$0.001/subcap; digest runs with `DIGEST`; integration test asserts call count per tier.

**Determinism — defect.** Today `temperature=0.0` is the only knob; `n_samples=1`. Spec wants multi-sample for HIGH+ tiers. Add ADR-0009 (below) + `multi_sample_run`:
```python
def multi_sample_run(req, *, n: int = 3) -> list[LlmResponse]:
    responses = [llm_call(LlmRequest(**{**req.__dict__, "temperature": 0.3})) for _ in range(n)]
    # Aggregate via embedding-cluster majority; flag CONTESTED if no cluster majority
    return responses
```
**AC**: HIGH tier runs n=3 samples; final claim survives if ≥2/3 cluster within cosine distance 0.1; otherwise `claim_state=CONTESTED`.

**Step 4 triangulation primary-source dedup — defect (P0).** Today three citations to FFIEC, OCC press release, and OCC blog look like 3-source corroboration; they're n=1 (OCC). 

**Fix**: every source carries a `primary_source_id`; triangulation deduplicates on it before counting:
```python
def triangulate(claim: dict, sources: list[dict]) -> int:
    primaries = {s.get("primary_source_id") or s["id"] for s in sources}
    return len(primaries)  # effective N
```
**AC**: golden test `golden_triangulation.json` with 10 cases; for each, effective_N = unique primary_source_id count.

**Step 5 contradiction rules — defect.** Rule 1 "higher tier wins" misses retractions. Insert "later contradicts earlier" override:
```python
def resolve_contradiction(a: dict, b: dict) -> dict:
    # 0. retraction trumps anything
    if "retract" in (b.get("text", "").lower()): return b
    if "retract" in (a.get("text", "").lower()): return a
    # 1. tier (T1 > T2 > T3 > T4 > T5)
    # 2. recency (within tier)
    # 3. independence (more independent primary sources wins)
    # 4. flag CONTESTED if all tied
    ...
```

### 2.3 Validation gates

**Implemented vs spec — defect (P0 BLOCKING).**

| Spec G# | Spec name | Implemented | Gap |
|---------|-----------|-------------|-----|
| G1 | Semantic novelty | ✓ `gate_novelty` (output not duplicate of recent runs) | OK |
| G2 | Source-quality minimums (≥1 T1 OR ≥2 T2) | ✗ | **Implement** |
| G3 | ERS ≥ threshold (with 0.35/0.25/0.20/0.20 weights) | ✗ | **Implement** |
| G4 | Independence (≥2 independent sources) | ✗ | **Implement** |
| G5 | Consistency (no internal contradictions) | ✗ | **Implement** |
| G6 | Adversarial verdict | ✓ via `consultant_loop._adversarial` (but not a gate row) | Surface as `gate_adversarial` |
| G7 | Drift (within 2σ of historical) | ✗ | **Implement w/ bootstrap baseline** |
| G8 | Absence proof | ✗ | **Implement** |
| —  | schema | ✓ extra | Keep as G0 / pre-flight |
| —  | citation, hallucination, freshness, bias, breaking_change, peer_coverage | ✓ extras | Re-frame as auxiliary checks; main gate engine = G1-G8 |

**Fix — replace `validation_gates_service.py` gate implementations:**
```python
def gate_g1_novelty(out, recent_outputs) -> GateResult: ...
def gate_g2_source_quality(out, sources) -> GateResult:
    tiers = Counter(s.get("tier") for s in sources)
    if tiers.get("T1", 0) >= 1 or tiers.get("T2", 0) >= 2:
        return GateResult("g2_source_quality", "pass", 1.0, ...)
    return GateResult("g2_source_quality", "fail", 0.0,
                      f"need ≥1 T1 or ≥2 T2; got {dict(tiers)}", ...)

def gate_g3_ers(out, sources, threshold: float = 0.55) -> GateResult:
    weights = {"recency": 0.35, "tier": 0.25, "independence": 0.20, "specificity": 0.20}
    # Calibrate weights against golden_ers.json
    ers = sum(weights[k] * _component(k, out, sources) for k in weights)
    return GateResult("g3_ers", "pass" if ers >= threshold else "fail",
                      ers, f"ERS={ers:.2f} threshold={threshold}", ...)

def gate_g4_independence(out, sources) -> GateResult:
    primaries = {s.get("primary_source_id") or s["id"] for s in sources}
    if len(primaries) >= 2: return GateResult("g4_independence", "pass", 1.0, ...)
    return GateResult("g4_independence", "fail", 0.0, ...)

def gate_g5_consistency(out) -> GateResult:
    # Pairwise NLI over claims; flag if any pair is "contradiction"
    ...

def gate_g7_drift(out, *, history_window_days: int = 30) -> GateResult:
    history = repo.list("reasoning_chains", {"started_at": {"$gte": cutoff}})
    if len(history) < 50: return GateResult("g7_drift", "warn", 0.5,
                                            "warming_up; <50 historical runs", ...)
    mean, std = _historical_distribution(history)
    z = abs((out_score - mean) / max(std, 0.01))
    return GateResult("g7_drift", "pass" if z <= 2 else "warn", ...)

def gate_g8_absence(out, sources, *, k: int = 5, window_days: int = 90) -> GateResult:
    # When the loop concludes "no evidence found," demand k T1/T2 negative searches
    ...
```
**AC**: `tests/unit/test_validation_gates.py` covers G1–G8 individually with per-gate golden cases; existing 6 auxiliary gates renamed to `aux_*`; consultant_loop output reports `{gates: {g1: ..., g2: ..., ..., g8: ..., aux: {...}}}`.

**Gate ordering DAG**: G1 → G2 → G3 → G4 → G5 → G6 (consumes G1–G5 outputs) → G7 (consumes G6 verdict) → G8 (independent). Today gates run in arbitrary order; document the DAG.

**Failure remediation per-gate** (specify in `validation_gates_service.py`):
| Gate | On fail |
|------|---------|
| G2  | Downgrade claim_label to HYPOTHESIS; surface as research candidate |
| G3  | Downgrade ERS-derived confidence; do not block |
| G4  | Mark as `single_source_evidence`; require human confirm before publish |
| G5  | Enter contradiction-resolution flow |
| G6  | If `degraded=false`: block. If `degraded=true`: hold; re-run when Anthropic recovers |
| G7  | Banner "drift detected"; do not block |
| G8  | Allow with `claim_label=CEILING_ESTIMATE` and explicit absence note |

### 2.4 Canonical sources

**ToS risk — defect (P1).** `config/canonical_sources.yml` includes LinkedIn / Indeed / BuiltWith via `polling_method: scrape` with no ToS sign-off field. **Fix**: add `tos_status: ['officially-licensed','data-broker','accepted-risk','disabled']`. Refuse to ingest from `disabled`. Default LinkedIn/Indeed/Glassdoor to `disabled` until officially licensed.

**JS-render fallback — defect (P2).** `feedparser` covers RSS only. Add `polling_method: playwright_scrape` option + headless browser worker; rate-limit at 1 req / 5s.

**Per-source rate limits — defect (P1).** Add to schema:
```yaml
- id: american_banker
  ...
  max_requests_per_minute: 10
  max_concurrent: 2
  backoff_policy: exponential
  retry_after_respect: true
```

**Source circuit breakers — defect (P1).** Add to source registry: `cb_state: closed|open|half_open`, `cb_open_until: <iso>`, `consecutive_failures`. After 5 consecutive 429s/5xx → open for 1h.

**Independence class — defect (P0).** Add `independence_class: ['regulator','self','licensee_of:<id>']` to every source. Triangulation step 4 dedups by class.

### 2.5 Capability map + drilldowns

**Pillar 1 node count** at 4014 (we measured), well under 5K. Cytoscape OK. Profile when P2-P4 land.

**Cose-bilkent layout** is on the frontend. Cache positions in Firestore `kg_layouts/{snapshot_id}/{lens_id}` with a TTL of 1 quarter. Re-layout on KG version bump only.

**URL state schema — defect (P1).** Document at `frontend/src/lib/url-state.ts`:
```
?lens=cluster&sub=WM&drill=D3&path=Cluster:VCC-04|Subvertical:WM|Subcap:P1C2.7.1
```
Test: copy URL → paste in fresh browser → exact same view.

**Reverse drilldown D2** (leaf → root) requires inverse indexes. Cost: ~50 KB/pillar in Firestore; trivial.

**"Find shortest path" right-click** — backend it. Today `graph_service.shortest_path` runs in 100ms for the Pillar 1 graph. Loading state on the UI; cap at 6 hops.

### 2.6 Knowledge graph

**28 vs 14 node types — defect (P0 partial).** Spec lists Vendor, Event, Benchmark, Suggestion, ReasoningChain, AuditFinding, ClientJourney, DMA-Packet, Story (raw), CrossPillarStory, etc. Implementation has only the catalogue spine. Add as nodes (one upsert pass per service):
```python
# graph_service._build_cached patch
for v in repo.list("vendor_profiles"):
    g.add_node(_nid("Vendor", v["vendor_id"]), kind="Vendor", **v)
for e in repo.list("vendor_events"):
    g.add_node(_nid("Event", e["id"]), kind="Event", **e)
    g.add_edge(_nid("Event", e["id"]), _nid("Vendor", e["vendor_id"]),
               kind="ABOUT_VENDOR")
# … similarly for Benchmark, Suggestion, ReasoningChain, AuditFinding
```
**AC**: `graph/summary` emits `nodes_by_type` with ≥ 22 distinct kinds (the 28 spec target minus L4/Story which are already there); contract test asserts each kind has ≥ 0 instances and edge schema conforms.

**Promotion rollback** — defect (P1). When a corroborating source retracts, `claim_state` should demote. Today there's no demotion handler. Implement in `services/knowledge_maturation.py`:
```python
def on_source_retraction(source_id: str) -> dict:
    affected_edges = [e for e in repo.list("graph_edges")
                      if source_id in (e.get("source_ids") or [])]
    for e in affected_edges:
        new_label = _recompute_label(e, exclude=source_id)
        if new_label != e["claim_label"]:
            repo.upsert("graph_edges", e["id"], {**e, "claim_label": new_label})
            publish_event("edge.demoted", {...})
```

**Entity resolution precision/recall — defect (P1).** Today `entity_resolver.py` uses rapidfuzz threshold 92 with a manual alias table. **No precision/recall on labelled set.** Add `golden_entity_resolution.json` with 50 pairs (positives + adversarial negatives like "Wells Fargo" vs "Wells Fargo Advisors") and report metrics.

**`SEMANTICALLY_SIMILAR` cosine threshold — defect (P1).** Threshold 0.85 asserted not calibrated. Run on labelled pairs from gen_stories (similar by `cap_id` = positive), tune to F1 ≥ 0.85.

**Firestore 1MB doc limit on `subcaps_graph`** — defect (P0). Today the graph is in-process only. To meet spec persistence: shard nodes/edges by pillar:
```
graph_snapshots/{snapshot_id}/nodes_p1   (~ 4014 docs / 200 per doc = 20 docs)
graph_snapshots/{snapshot_id}/edges_p1   (~ 12249 docs / 500 per doc = 25 docs)
```
**AC**: `graph_service.persist_snapshot(snapshot_id)` writes ≤ 50 Firestore docs each ≤ 900 KB; `graph_service.load_snapshot(snapshot_id)` round-trips identically.

### 2.7 Benchmark engine

**PDF extraction error rate — defect (P0).** Required: build a 20-PDF labelled set (curated snippets with ground-truth numerics); measure character-level + numeric-format error rate on Document AI output. Add a dimensional validator after extraction:
```python
def validate_metric(value: float, metric_id: str) -> tuple[bool, str | None]:
    rules = METRICS[metric_id]["validation_rules"]
    for rule in rules:
        if rule.startswith(">="):  bound = float(rule[3:].rstrip("%"))
        # …
    if not (lo <= value <= hi): return False, f"out of range [{lo},{hi}]"
    return True, None
```
**AC**: `benchmarks_service._ingest_filings` rejects values outside `validation_rules`; flagged values land in `benchmark_validation_errors` collection.

**IID violation in bootstrap — defect (P0).** `_compute_distribution` uses `statistics.pstdev` on N values. Replace with hierarchical bootstrap:
```python
def hierarchical_bootstrap_ci(observations: list[dict],
                              *, B: int = 1000, ci: float = 0.90) -> dict:
    """Cluster by primary_source_id; bootstrap with replacement at cluster level."""
    by_primary = {}
    for o in observations:
        by_primary.setdefault(o.get("primary_source_id") or o["id"], []).append(o)
    primaries = list(by_primary.keys())
    samples = []
    for _ in range(B):
        chosen = random.choices(primaries, k=len(primaries))
        flat = [o for p in chosen for o in by_primary[p]]
        if flat: samples.append(statistics.median(o["value"] for o in flat))
    samples.sort()
    lo, hi = samples[int(B * (1 - ci) / 2)], samples[int(B * (1 + ci) / 2)]
    return {"median": statistics.median(samples), "ci_low": lo, "ci_high": hi,
            "effective_n": len(by_primary)}
```
**AC**: `benchmark_distributions[*].effective_n ≤ N` whenever multiple observations share `primary_source_id`; CI width ≥ naive CI.

**Cohort assignment as inference — defect (P1).** Today `_company_cohorts` uses static membership rules. When LLM-assisted (live mode), pass through G1–G6.

**Adversary verdict thresholds calibration — defect (P1).** Run `_compute_distribution` against 20 FDIC-published statistics (ground truth public); verdict must agree with truth ≥ 90%. Persist calibration table.

**DocAI cost — defect (P1).** Add to `cost_tracking`: `service: "docai", pages_processed: N, cost_usd: pages*0.03`. Quarterly forecast: 200 SOWs × 50 pages = 10K pages × $0.03 ≈ $300/quarter. Spec's $1,200/quarter forecast assumed 4× pages; document the actual.

### 2.8 Quarterly digest

**Opus budget vs digest run** — see §2.1 above; **fix is mandatory**. Pick one of three paths.

**Per-priority adversarial cost.** 50 priorities × Sonnet at 4K/0.5K = 250K in / 25K out = within Sonnet daily (3M / 500K). OK.

**Regression on golden quarters — defect (P0).** Curator named, scope undocumented. Specify: 5 historical quarters × 5 priorities/subvertical × 10 subverticals = 250 labels. Curator: principal consultant + Pillar Lead. Validation: 2-of-3 agreement. Refresh: quarterly during live ops.

**Subvertical priorities format — defect (P1).** Lock with Pydantic + JSON Schema; bump version on breaking change:
```python
# backend/app/models/digest.py
class DigestPriority(BaseModel):
    schema_version: Literal["digest-priority-v1"] = "digest-priority-v1"
    sub_cap_id: str
    sub_cap_name: str
    state: LifecycleState
    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    narrative: str = Field(min_length=40)
    recommendation: str = Field(min_length=40)
    evidence_sows: list[SowEvidence]
    evidence_benchmarks: list[BenchmarkEvidence]
    evidence_news: list[NewsEvidence]
    delta: PriorityDelta | None = None
    chain_id: str | None = None
    cost_usd: float = Field(ge=0)
    claim_labels: list[ClaimLabel] = Field(min_length=1)
```
**AC**: `digest_service.generate` validates output against `DigestPriority`; CI fails if any breaking change without version bump.

**Cross-pillar coherence — defect (P1).** Today: Sonnet call with no rule layer. Add rule-first:
```python
def coherence_check(priorities_by_subvertical: dict) -> list[dict]:
    issues = []
    seen_actions = {}
    for sv, pri_list in priorities_by_subvertical.items():
        for p in pri_list:
            for a in p.get("recommendations") or []:
                target = (a.get("target"), a.get("kind"))
                if target in seen_actions:
                    other_sv, other_kind = seen_actions[target]
                    if _conflicts(a["kind"], other_kind):
                        issues.append({"target": target, "subverticals": [sv, other_sv], ...})
                seen_actions[target] = (sv, a["kind"])
    return issues
```
LLM only as tiebreaker on rule-flagged issues.

### 2.9 Lifecycle engine

**Weight calibration — defect (P0).** Spec weights (25/15/15/15/15/15) are uncalibrated. Build `golden_lifecycle_decisions.json` (50 subcap states from past Zennify quarterly reviews). Solve `argmin_w sum(|predicted_state - actual_state|)` via grid search or scipy.optimize. Refit quarterly.

**Maturity-gap upstream confidence — defect (P1).** `lifecycle_service._gather_signals` consumes benchmark verdict counts but ignores per-distribution CI width. Pipe through:
```python
sig.benchmark_avg_ci_width = mean(d.get("ci_width") for d in distributions)
# and downgrade lifecycle_decision when ci_width > 0.4
```

**Decay vs inactive — defect (P1).** Today both are leaf states with no transition. Add temporal rule:
```
DECAY → INACTIVE if no signal for 12 months AND no prospect SOW
INACTIVE → RETIRED if 24 months in INACTIVE
```

### 2.10 What-if simulator

**Concurrency — defect (P1).** Today single-user assumed. Add `simulation_id` + `created_by` + version-locking on `lifecycle_scores`:
```python
def simulate(actions, *, base_snapshot_id: str | None = None) -> dict:
    if base_snapshot_id != current_snapshot_id():
        raise ConflictError("snapshot moved; rebase your simulation")
    ...
```

**Per-user-per-day budget — defect (P2).** Add `whatif_cost_tracker` collection; cap at $5/user/day.

### 2.11 Hallucination + citation verifier

**LLM-on-LLM circularity — defect (P1).** `gate_hallucination` is rule-based (salient-token overlap), good. But when the LLM is invoked in live mode for tiebreak, document the loop bound.

**False-negative rate target — defect (P0).** Build `golden_hallucination_set.json` (200 good + 50 known-hallucinated); achieve recall ≥ 0.95 on hallucinations, precision ≥ 0.90. Block CI if degraded.

### 2.12 Project structure

**100+ Python modules — current 32 services + 30 routers + 14 jobs + 5 llm.** Spec target met.

**Layering enforcement — defect (P1).** Add `import-linter` config:
```ini
# backend/.import-linter
[importlinter]
root_package = app

[importlinter:contract:layered]
name = Layered architecture
type = layers
layers =
    api
    services
    services.llm
    models
ignore_imports =
    app.services -> app.services
```
**AC**: CI fails if `api` imports a private service module or `services` imports `api`.

**DI consistency — defect (P2).** FastAPI `Depends` is the de facto IoC. Document in ARCHITECTURE; ban service-locator patterns.

### 2.13 Observability

**SLOs — defect (P0).** Add to `RUNBOOK.md`:
| Endpoint | p50 | p95 | p99 | Error budget |
|----------|-----|-----|-----|--------------|
| `/api/health` | 5ms | 30ms | 50ms | 0.1% |
| `/api/catalogue/*` | 80ms | 300ms | 500ms | 0.5% |
| `/api/digest/{id}` (cached) | 100ms | 800ms | 1.5s | 1% |
| `/api/digest/generate` | async; 6h SLA | — | — | 5% |
| `/api/chat/messages` | 1.5s | 5s | 12s | 1% |
| `/api/graph/*` | 200ms | 1s | 2s | 1% |
| `/api/graph/path` | 400ms | 1s | 2s | 1% |

Tie SLOs to error budgets via Cloud Monitoring SLO objects. Block deploys when budget exhausted (Cloud Build step: `gcloud monitoring slos describe ... --format='value(error_budget_remaining)' | xargs -I% test % -gt 0`).

**Trace continuity on jobs — defect (P1).** Cloud Scheduler → Cloud Run Job: propagate `traceparent` header from Scheduler attributes; runner reads it via `request.headers` (Cloud Run Jobs receive HTTP via the per-execution proxy). Add to `app/jobs/runner.py`:
```python
import os
from opentelemetry import trace, context

trace_parent = os.getenv("TRACEPARENT")
if trace_parent:
    ctx = TraceContextTextMapPropagator().extract({"traceparent": trace_parent})
    context.attach(ctx)
```

### 2.14 Reliability

**RPO 24h — defect (P1).** Spec implicit RPO is 24h via Firestore daily export; that's our weakest link. **Enable Firestore PITR** (point-in-time recovery — generally available since 2024) for 7-day retention; RPO collapses to ~1 minute. Cost: $X/GB-month (negligible at our scale).

**DR drill cadence — defect (P1).** Specify in `RUNBOOK.md`: quarterly DR drill; evidence = restore log, RTO measurement, sign-off.

**Graceful-degradation contract — defect (P1).** Per external dep:
| Dep | Detection | Fallback | UI banner | Max duration |
|-----|-----------|----------|-----------|--------------|
| Anthropic | 503 / 429 / latency p95 > 30s | Gemini Pro | "Reasoning degraded — Sonnet unavailable" | 24h before page |
| Vertex Gemini | same | dev-mode canned (read-only) | "Live LLM unavailable; site read-only" | 4h |
| Drive | 5xx for 5 min | fall back to last cached snapshot | "Catalogue refresh paused" | 24h |
| Firestore | latency p95 > 1s | read-only banner | "Writes paused for stability" | 1h |
| Vector Search | 5xx | BQ ML.DISTANCE | "RAG degraded" | 24h |

### 2.15 Testing

**Golden datasets — defect (P0 BLOCKING).** None committed. Required files:
- `test-data/eval/golden_pillar1_v14.0.json` (Batch 1 parser regression)
- `test-data/eval/golden_diff_narratives.json` (10 entries; Batch 4 narrative regression)
- `test-data/eval/golden_subcap_extraction.json` (100 SOW chunk → ground truth labels)
- `test-data/eval/golden_entity_resolution.json` (50 entity pairs)
- `test-data/eval/golden_adversarial_critiques.json` (30 adversary recall tests)
- `test-data/eval/golden_hallucination_set.json` (200 good + 50 bad)
- `test-data/eval/golden_triangulation.json` (10 cases)
- `test-data/eval/golden_benchmark_inference.json` (50 ground-truth pairs)
- `test-data/eval/golden_lifecycle_decisions.json` (50 subcap states)
- `test-data/eval/golden_digest_priorities.json` (5 quarters × 10 subverticals × 5 priorities = 250 labels)
- `test-data/eval/golden_contradiction_resolutions.json` (30)

**Eval token budget — defect (P1).** Reserve 2% of weekly LLM budget for eval; `eval_run_weekly` job runs in a dedicated `cost_tracking` bucket.

**Property tests — defect (P1).** Add `hypothesis` to requirements; cover: parser (random rows), ERS calculator (random tier mixes), peer cohort assignment (random asset sizes), contradiction resolver (random tier pairs).

**Mutation tests — defect (P1).** `mutmut` over `validation_gates_service.py` + `consultant_loop.py`; mutation-kill rate ≥ 0.85.

### 2.16 Acceptance criteria — see §9 below for the rewritten 40

---

## §3. Per-Batch QA Report (verdicts)

| Batch | Pre-cond | F | N | A | Regression hooks | DoD verdict |
|-------|----------|---|---|---|------------------|-------------|
| 0 | ✓ | ✓ all 6 stub patterns | ✓ image < 600 MB; cold start < 200 ms; pytest 30 s | A0.1 fails: AUTH_MODE=dev not blocked from prod profile | none yet | **Partial** — A0.1 + A0.5 (non-root) untested; no `import-linter` |
| 1 | ✓ Drive token, P1 file present | ✓ ingest 199/4/36/827/1852/4844 | ✓ ingest 127 s on dev (over spec 60 s budget — see fix) | A1.6 untested (synthetic P2) | golden file missing | **Defect (P1)** — ingest > 60 s budget; **A1.6 P2 onboarding NOT TESTED** |
| 2 | ✓ | ✓ 4014 nodes / 12249 edges; lenses; centrality | ✓ build 90 ms cold; render targets met | A2.6 embedded QA NOT IMPLEMENTED | golden KG snapshot missing | **Defect (P0)** — only 14 of 28 spec node types; no self-test |
| 3 | ✓ | ✓ 4 SOWs, redaction, mention extract; 4844 stories | ✓ DocAI cost untracked separately | A3.1 PII test pack absent; A3.6 self-test absent | none | **Defect (P0)** — A3.1 not run; entity resolver precision unmeasured |
| 4 | ✓ | ✓ 7-step loop, 8 (wrong) gates, suggestions | ✓ chain ≤ 3 s in dev | A4.5 adversary collusion untested; A4.7 triangulation spoof untested | none | **Defect (P0 BLOCKING)** — gates wrong (G1-G8 not matched); no leverage tier; no multi-sample |
| 5 | ✓ | ✓ filings + analyst + technographics; 20 distributions | naive CI not hierarchical | A5.1 IID untested; A5.6 self-test absent | none | **Defect (P0)** — non-hierarchical bootstrap |
| 6 | ✓ | ✓ lifecycle scoring, vendor heatmap, journey, DMA packet | ✓ recompute 200 ms for 199 subcaps | A6.1 weight calibration untested; A6.4 demotion rollback absent | none | **Defect (P1)** — uncalibrated weights |
| 7 | ✓ | ✓ digest + PPTX + audit | **Opus budget MATH FAILS** (see §2.1) | A7.1 budget overrun NOT HANDLED (single-day single-shot today) | none | **Defect (P0 BLOCKING)** — Opus budget |
| 8 | ✓ | ✓ chat, what-if, personas, exports, eval | ✓ all green | A8.5 self-test absent | golden datasets absent | **Defect (P0)** — golden eval data absent |
| 9 | ✓ | ✓ 14 jobs, OTel hook, IaC, scheduler | SLOs absent | A9.1-A9.6 chaos drills not run; A9.6 GDPR purge untested | none | **Defect (P1)** — no SLOs, no chaos drill |

**Headline**: 4 batches ship at P0-blocking defect, 4 at P1. Ship is gated by these.

---

## §4. Cross-Cutting Audits

| Item | Required deliverable | Status | Evidence | Fix |
|------|---------------------|--------|----------|-----|
| 4.1 Pillar-1 as canonical schema | Synthetic P2 ingest succeeds zero-code | **Not tested** | Ingest is data-driven, but no synthetic-P2 acceptance test | Build `tests/integration/test_pillar2_synthetic.py`: clone P1, rename IDs to P2, ingest, assert KG re-builds with both pillars |
| 4.2 Pre-trained capability clusters | `services/cluster_service.py` | **Missing (P0)** | No cluster service exists | See §5 for design + interfaces |
| 4.3 Cross-pillar integration module | `services/cross_pillar_integration.py` | **Missing (P0)** | Not implemented | See §5 |
| 4.4 Embedded QA per component | `self_test_passed: bool` on every emit | **Missing (P0)** | No service emits a self-test record | Add `mixins/embedded_qa.py` (below) |
| 4.5 Reasoning chain on every analytical op | `reasoning_chains/{run_id}` | **Partial** | `consultant_loop.run` writes chains; lifecycle/benchmarks don't go through the loop | Wrap lifecycle scoring + benchmark verdict assignment in `loop.run` with `LeverageTier.LOW` |
| 4.6 Reproducibility manifest | `manifest.json` per run | **Missing (P0)** | No manifest emission | Add `app/observability.py::emit_manifest(run_id, **fields)` |
| 4.7 Cost attribution | `(operation_type, pillar, subvertical, subcap_id?, batch?)` on every LLM call | **Missing (P1)** | Cost tracker logs only `model + tokens + cost` | Patch `cost_tracker.record` signature (see §2.1) |
| 4.8 Schema evolution | `_schema_version` on every collection + Pydantic model | **Missing (P0)** | Only `dma-handoff-v1` has it | Add `_schema_version` to every Pydantic model in `app/models/`; migration test in CI |

### Embedded QA mixin

```python
# backend/app/mixins/embedded_qa.py
from dataclasses import dataclass, field
from typing import Callable, Any

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

def run_self_test(payload: dict, checks: list[tuple[str, Callable[[dict], bool], str]]) -> EmbeddedQAResult:
    log = [Check(name=name, passed=fn(payload), detail=msg) for name, fn, msg in checks]
    return EmbeddedQAResult(self_test_passed=all(c.passed for c in log), self_test_log=log)
```

**AC**: every service that emits a domain object (digest, suggestion, chain, distribution, journey, DMA packet) calls `run_self_test` and persists the result; CI assertion: `repo.list("<collection>")[*].self_test_passed must be True or service refused to emit`.

### Reproducibility manifest

```python
# app/observability.py — addition
import hashlib, json, subprocess
from datetime import datetime, timezone

def emit_manifest(run_id: str, **fields) -> dict:
    manifest = {
        "run_id": run_id,
        "git_sha": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
        "model_versions": {
            "anthropic_sonnet": get_settings().anthropic_model_sonnet,
            "anthropic_opus": get_settings().anthropic_model_opus,
            "gemini_pro": get_settings().gemini_model_pro,
            "gemini_flash": get_settings().gemini_model_flash,
            "vertex_embedding": get_settings().vertex_embedding_model,
        },
        "prompt_versions": _get_prompt_hashes(),
        "config_hash": hashlib.sha256(json.dumps(get_settings().model_dump(), sort_keys=True, default=str).encode()).hexdigest()[:16],
        "rng_seed": fields.get("rng_seed"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **fields,
    }
    get_repository().upsert("reproducibility_manifests", run_id, manifest)
    return manifest
```

---

## §5. Catalog & Cluster Architecture

### Pydantic models (drop into `backend/app/models/catalogue.py`)

```python
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict
from .common import ClaimLabel, SourceTier, MaturityLevel

class Subcap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["subcap-v1"] = "subcap-v1"
    sub_cap_id: str = Field(pattern=r"^P[1-4]C\d+\.\d+\.\d+$")
    sub_cap_name: str
    pillar_id: str = Field(pattern=r"^P[1-4]$")
    category_id: str
    l1_capability: str
    description: str
    solution_type: Literal["Hybrid", "Software", "Service"]
    tier: Literal["T1", "T2", "T3"]
    personas: list[str]
    l3_platforms: list[str]
    l4_features: list[str]

class CapabilityCluster(BaseModel):
    schema_version: Literal["cluster-v1"] = "cluster-v1"
    cluster_id: str
    name: str
    centroid: list[float] = Field(min_length=256, max_length=256)  # 256-dim embedding
    member_subcap_ids: list[str]
    purity: float = Field(ge=0, le=1)
    last_updated_at: str
    drift_history: list[dict] = []
```

### Cluster service interface

```python
# backend/app/services/cluster_service.py
from typing import Protocol

class ClusterService(Protocol):
    def bootstrap_clusters_from_pillar1(self, *, n_clusters: int = 12) -> list[CapabilityCluster]:
        """Build initial cluster set from Pillar 1 catalogue using K-Means on embeddings."""
    def assign_to_cluster(self, capability: dict, *, threshold: float = 0.75) -> tuple[str | None, float]:
        """Returns (cluster_id, similarity) or (None, similarity) if below threshold (novel cluster candidate)."""
    def update_centroids(self) -> dict:
        """Re-fit centroids from current member set; emits drift report."""
    def detect_drift(self, *, window_days: int = 90) -> list[dict]:
        """Return clusters whose centroid moved >0.05 cosine in window."""
    def propose_new_cluster(self, capability: dict, *, novelty_threshold: float = 0.7) -> dict | None:
        """When a capability fails to assign with similarity ≥ threshold, propose a novel cluster."""
```

**AC**: bootstrap on Pillar 1 produces ≥ 8 clusters with purity ≥ 0.7 (use UC tag families as ground truth labels for purity); centroid drift < 0.05 cosine over a quarter under stable input; novel-cluster proposal triggers a `cluster.proposed` Pub/Sub event.

### Cross-pillar integration module

```python
# backend/app/services/cross_pillar_integration.py
from typing import Protocol

class CrossPillarIntegration(Protocol):
    def ingest_new_pillar(self, catalog_path: str, *, pillar_id: str) -> "DeltaReport":
        """End-to-end: validate, embed, cluster, link, emit delta. NO writes without approval."""
    def validate_against_canonical_schema(self, parsed: ParseResult) -> list["SchemaDeviation"]:
        """Compare against `subcap-v1` and friends; return per-row deviations."""
    def embed_and_assign(self, capabilities: list[dict]) -> list[tuple[dict, str | None]]:
        """Embed each capability; assign to existing cluster or flag novel."""
    def link_into_kg(self, parsed: ParseResult, *, dry_run: bool = True) -> "GraphDelta":
        """Compute the node/edge delta against the current KG; do not commit if dry_run."""
    def recompute_graph_density(self, before: dict, after: dict) -> dict:
        """Density metrics (avg degree, clustering coef, modularity) before/after."""
    def emit_delta_report(self, *, dry_run_id: str) -> "DeltaReport":
        """Emit the full report for human approval; gate the actual ingest behind a separate apply()."""

class DeltaReport(BaseModel):
    schema_version: Literal["delta-report-v1"] = "delta-report-v1"
    pillar_id: str
    new_nodes: list[dict]
    new_edges: list[dict]
    schema_deviations: list[SchemaDeviation]
    novel_clusters: list[dict]
    graph_density_before: dict
    graph_density_after: dict
    estimated_cost_usd: float
    requires_approval: bool = True
```

**AC**: drop a P2 catalog file → `ingest_new_pillar(dry_run=True)` returns `DeltaReport`; CI passes only if `schema_deviations == []`; `apply()` requires `approved_by` field set.

### Sequence — onboard P2

```
operator                 cross_pillar_integration             cluster_service             knowledge_maturation
   │ POST /pillars/P2/dry-run   │                                    │                              │
   ├──────────────────────────► │                                    │                              │
   │                            │ validate_against_canonical_schema  │                              │
   │                            │ embed_and_assign(capabilities) ──► │                              │
   │                            │                                    │ assign_to_cluster(c)         │
   │                            │ ◄────────────────────────────────  │                              │
   │                            │ link_into_kg(dry_run=True) ─────────────────────────────────────► │
   │                            │ recompute_graph_density                                          │
   │ ◄── DeltaReport ──────────  │                                    │                              │
   │ POST /pillars/P2/apply     │                                    │                              │
   │ {approved_by: "alice"}     │                                    │                              │
   ├──────────────────────────► │ commit nodes + edges + clusters    │                              │
```

---

## §6. Fix-and-Enhancement Plan

| # | Module / Batch | Goal state | Tasks (≤1d each) | AC | Deps | Risk | Effort | Priority |
|---|----------------|-----------|------------------|-----|------|------|--------|----------|
| 1 | `validation_gates_service.py` (Batch 4) | G1–G8 match spec | (a) rename auxiliary gates to `aux_*`; (b) implement G1-G5 + G7 + G8; (c) per-gate failure remediation table; (d) gate DAG document | All 8 spec gates emit; `tests/unit/test_validation_gates.py` covers each | none | low | M | **P0** |
| 2 | `app/mixins/embedded_qa.py` (cross-cut) | Every service emits `self_test_passed` | Build mixin; wire to digest, suggestion, chain, distribution, journey, DMA packet emit paths | CI assertion: every domain row has `self_test_passed: True` | 1 | low | M | **P0** |
| 3 | `app/observability.py::emit_manifest` (cross-cut) | Reproducibility manifest per analytical run | Add module; call from `consultant_loop.run` end | `reproducibility_manifests` populated; replay test passes | 1 | low | S | **P0** |
| 4 | `app/models/*` schema versioning | Every Pydantic model + collection has `_schema_version` | Add to common.py + per-domain models; migration test | `pytest tests/unit/test_schema_versions.py` green | none | low | S | **P0** |
| 5 | `services/cluster_service.py` (new) | Pre-trained Pillar-1 clusters | (a) Pydantic model; (b) interface; (c) bootstrap on P1; (d) golden purity test | Bootstrap ≥ 8 clusters purity ≥ 0.7 | embedding service | medium | L | **P0** |
| 6 | `services/cross_pillar_integration.py` (new) | P2/P3/P4 onboarding without code change | (a) interface; (b) dry_run returns DeltaReport; (c) apply requires approver; (d) synthetic P2 acceptance | `tests/integration/test_pillar2_synthetic.py` passes | 5 | medium | L | **P0** |
| 7 | `digest_service.py` (Batch 7) | Opus budget never overrun | (a) checkpointed multi-day run; (b) ADR-0011; (c) downgrade to Sonnet for per-subvertical synthesis when budget tight; (d) DigestPriority Pydantic model | `digest_run.checkpoint` event emitted on budget; replay test passes | 4 | medium | M | **P0** |
| 8 | `consultant_loop.py` (Batch 4) | Leverage tiers + multi-sample + primary-source dedup + retraction-aware contradiction rules | (a) `LeverageTier` enum + dispatch; (b) `multi_sample_run`; (c) triangulation dedup by `primary_source_id`; (d) contradiction order with retraction override; (e) ADR-0008 + ADR-0009 | per-tier call-count contract test; multi-sample non-determinism contract test | 1 | low | M | **P0** |
| 9 | Golden datasets (cross-cut) | All 11 golden files committed | (a) `golden_pillar1_v14.0.json`; (b) `golden_diff_narratives.json`; (c) `golden_subcap_extraction.json`; ... (k) `golden_contradiction_resolutions.json` | Eval harness loads each; per-dataset passes | 1, 2 | medium (curation) | L | **P0** |
| 10 | `benchmarks_service.py` (Batch 5) | Hierarchical bootstrap + dimensional validator + primary-source dedup | (a) `hierarchical_bootstrap_ci`; (b) `validate_metric` per metric_id; (c) primary-source field on every observation; (d) ADR-0010 | distribution rows include `effective_n` and `ci_low/ci_high`; OOR values rejected | none | low | M | **P0** |
| 11 | `graph_service.py` (Batch 2) | 28 spec node types + Firestore-sharded persistence + claim_state on edges | (a) extend `_build_cached` to add Vendor/Event/Benchmark/Suggestion/ReasoningChain/AuditFinding; (b) `persist_snapshot`/`load_snapshot` shard by pillar; (c) `claim_state` per edge; (d) `SEMANTICALLY_SIMILAR` cosine edge | `nodes_by_type` ≥ 22 kinds; round-trip persist/load identical | none | medium | L | **P0** |
| 12 | Cost attribution (Batch 4) | `(op, pillar, sv, subcap, batch)` on every call | Patch `cost_tracker.record` + every caller | Query: cost by subvertical for digest run returns exact answer | none | low | M | **P1** |
| 13 | SLO + error budgets (Batch 9) | Documented + enforced | Add to RUNBOOK; create Cloud Monitoring SLO objects; gate deploys | Cloud Build step blocks deploy when budget exhausted | none | low | M | **P0** |
| 14 | Source registry hardening (Batch 4) | `tos_status`, `independence_class`, rate limits, CB | Schema bump; per-source migration | `golden_canonical_sources.json` schema-validates | none | low | M | **P1** |
| 15 | Lifecycle weight calibration (Batch 6) | Calibrated weights + upstream confidence pipe-through | Build `golden_lifecycle_decisions.json`; grid-search weights; refit job | Agreement ≥ 80% on golden | 9 | medium | M | **P1** |
| 16 | Entity resolution metrics (Batch 3) | precision/recall on labelled set | Build `golden_entity_resolution.json` (50 pairs); add precision/recall test | precision ≥ 0.95 / recall ≥ 0.85 | 9 | medium | M | **P1** |
| 17 | DocAI dimensional validator (Batch 5) | Numeric extraction errors caught | Add `validate_metric`; flag to `benchmark_validation_errors` | OOR values rejected, logged | 10 | low | S | **P1** |
| 18 | Promotion / demotion handler (Batch 6) | `claim_state` transitions atomic + reversible | Add `knowledge_maturation.py::on_source_retraction`; demote on retraction | Test: promote to FACT, retract source, demoted to INFERENCE | 11 | low | S | **P1** |
| 19 | URL state schema (Batch 7 frontend) | Shareable deep-links survive | Implement `url-state.ts` + assertion test | Copy URL, paste in fresh browser, identical view | none | low | S | **P2** |
| 20 | DR drill + Firestore PITR (Batch 9) | RPO ≤ 1 min | Enable PITR; quarterly drill scheduled | Drill report attached | none | low | S | **P1** |

**Total effort**: ~14 engineer-days for the P0 set + ~6 days for P1.

---

## §7. Roadmap & Sequencing

**Critical path** (each box is a P0 fix; arrows = data dep):

```
[1 gates G1-G8] ──┐
                  ├─► [9 golden datasets] ──┐
[2 embedded QA] ──┤                          ├─► [16 entity res metrics]
                  │                          │
[3 manifest]    ──┤                          ├─► [15 lifecycle calibration]
                  │                          │
[4 schema ver]  ──┘                          ├─► [17 docai validator]
                                             │
[8 leverage tier + multi-sample] ────────────┘

[10 hierarchical bootstrap] ──────────► [7 digest checkpointing]

[5 cluster service] ──► [6 cross-pillar integration]

[11 graph 28 types]    [13 SLO + budgets]    [14 source registry]

[18 demote handler] (depends on 11)
```

**Suggested sequencing** (parallel-where-possible):

- **Sprint 1 (3 days)**: 1, 2, 3, 4, 8 + ADR-0008/0009 — closes the gate + reproducibility + claim hygiene gap.
- **Sprint 2 (3 days)**: 9 + 10 + 13 + 14 + 17 + ADR-0010 — closes evidence + cost + reliability gap.
- **Sprint 3 (4 days)**: 5 + 6 + 11 — closes the canonical-schema + cross-pillar gap.
- **Sprint 4 (2 days)**: 7 + 18 + 20 + ADR-0011 — closes Opus budget + promotion lifecycle + DR.
- **Sprint 5 (2 days)**: 12, 15, 16 + 19 — closes attribution + calibration + UX state.

---

## §8. Quality Gates & Continuous-Learning Loop

**Per-PR gates (CI):**
1. `pytest -q` ≥ 319 (current) + every new test green.
2. `vitest --run` 45 (current) + every new test green.
3. `import-linter --config backend/.import-linter` clean.
4. `mypy --strict backend/app/` clean (excluding TODOs).
5. `ruff check` clean.
6. Mutation kill rate on `validation_gates_service.py` + `consultant_loop.py` ≥ 0.85.
7. Schema-version migration test on every `app/models/*.py` change.
8. Golden eval drop ≤ 2% per dataset.
9. Cost-attribution contract test (every LLM call has `op, pillar, sv` tags).

**Continuous learning signals:**
- **Drift detection**: weekly `eval_run_weekly` job; if any golden dataset drops > 2% week-over-week → page on-call.
- **Cluster centroid drift**: monthly job emits drift_report; if > 0.05 cosine on any cluster → trigger re-fit.
- **Gate verdict distribution**: track `gate_pass_rate` per gate per week; alert if any gate's pass rate drops > 10pp.
- **Calibration refresh**: quarterly job re-fits ERS weights + lifecycle weights against latest golden labels; commit deltas to `calibration_history`.
- **Source ToS audit**: monthly cron checks every source's ToS-changed flag; alerts if any prior-licensed source is now unclear.

---

## §9. Updated Acceptance Criteria (replace §22)

40 ACs; every one measurable + tied to an SLO or test.

| # | AC | Test | SLO/Threshold |
|---|-----|------|---------------|
| 1 | `/api/health` returns 200 | smoke | p99 < 50 ms |
| 2 | Auth: Firebase token required in prod profile; AUTH_MODE=dev rejected | A0.1 | 100% rejection |
| 3 | Pillar parser: byte-identical output vs `golden_pillar1_v14.0.json` | R1.1 | exact match |
| 4 | SOW ingest end-to-end < 5 min for 50-page SOW | N3.1 | p95 < 300 s |
| 5 | Mission Control FCP on 4G simulation | Lighthouse | p95 < 1.5 s |
| 6 | Capability Explorer sunburst initial render at 836 leaves | N1.1 | < 600 ms p95 |
| 7 | Reasoning Chain Viewer renders 7 steps + claims + sources + 8 gates per chain | F4.4 | render < 800 ms p95 |
| 8 | Subcap edit + version snapshot + diff narrative | F1.7 | end-to-end < 5 s p95 |
| 9 | Knowledge Graph: ≥ 22 spec node kinds; 4014 / 12249 P1 baseline | F2.1 | ≥ 22 kinds |
| 10 | Lens stack switch | N2.4 | < 200 ms p95 |
| 11 | Sigma+WebGL fallback engages > 2K nodes with banner | A2.4 | banner shown |
| 12 | LLM router routes per matrix §3 with mocked providers | F4.1 | manifest match |
| 13 | 7-step loop end-to-end | N4.1 | p95 < 90 s |
| 14 | Cache hit rate per cacheable class | N4.2 | embeddings ≥ 95%, news cat ≥ 60%, similarity ≥ 70%, reasoning ≤ 5% |
| 15 | DLP false-negative on PII test pack | N3.3 | < 5% |
| 16 | Subcap mention extraction P/R | F3.2 | precision ≥ 0.85 / recall ≥ 0.75 |
| 17 | Entity resolution P/R | A3.3 | precision ≥ 0.95 / recall ≥ 0.85 |
| 18 | Benchmarks Studio: distribution + CI band + sources + verdict | F5.6 | < 800 ms p95; CI width disclosed |
| 19 | Adversary verdict calibration vs FDIC ground truth | A5.5 | ≥ 90% agreement |
| 20 | Quarterly digest: 10 SVs × ≥ 3 priorities × ≥ 3 evidence ERS ≥ 0.5 × adversarial sev ≤ MEDIUM | F7.1 | full schema-validated |
| 21 | Digest never overruns Opus daily budget | A7.1 | 0 overruns |
| 22 | Lifecycle scoring agreement vs golden | A6.1 | ≥ 80% |
| 23 | Vendor heatmap render | N6.2 | < 600 ms p95 |
| 24 | Client journey atlas + DMA packet schema validation | F6.5 | Pydantic-clean |
| 25 | Lifecycle promotion/demotion atomic | A6.4 | round-trip test passes |
| 26 | 8 gates emit pass/fail with reason for every analytical run | F4.5 | 100% coverage |
| 27 | Adversary recall on golden adversarial | A4.5 | ≥ 0.90 |
| 28 | Chat: hallucination rate on `golden_hallucination_set` | A8.1 | recall ≥ 0.95 / precision ≥ 0.90 |
| 29 | What-If sandbox concurrency | A8.2 | conflicts rejected with 409 |
| 30 | Persona privilege check | A8.3 | frontline cannot trigger admin |
| 31 | KG self-test on every build | A2.6 | 100% |
| 32 | Pillar-2 onboarding without code change | A2.3 + A1.6 | DeltaReport schema-validates |
| 33 | Reproducibility: replay-from-manifest semantic equivalence | §4.6 | embedding distance ≤ 0.1 |
| 34 | Cost attribution: query cost by subvertical for digest | §4.7 | exact answer |
| 35 | Schema migrations: every collection has `_schema_version` | §4.8 | 100% |
| 36 | Cluster service: bootstrap purity | §5 | ≥ 0.7 |
| 37 | Cross-pillar integration: DeltaReport for synthetic P2 | §5 | schema_deviations == [] |
| 38 | Anthropic weekly spend | COST_GUIDE | < $X/week |
| 39 | Daily total spend ceiling | COST_GUIDE | auto-throttle at 90% |
| 40 | Penetration test pass + OWASP top-10 + secrets scan + dependency CVE clean | A9.4 | 0 criticals |

---

## §10. Executive Summary — top 10 actions in priority order

| Rank | Action | Goal | AC | Batch | Effort |
|------|--------|------|-----|-------|--------|
| 1 | **Replace 8 gates with G1-G8 per spec §5** | True spec parity on validation | All 8 emit pass/fail/score with reason | Batch 4 | M |
| 2 | **Add embedded self-test mixin** | Every analytical emit is self-checked | `self_test_passed` true on 100% of new rows | cross-cut | M |
| 3 | **Reproducibility manifest** | Replay from any past run | semantic-equiv replay test passes | cross-cut | S |
| 4 | **Schema-versioned Pydantic + Firestore docs** | Every collection migrates safely | `_schema_version` on 100% | cross-cut | S |
| 5 | **Golden datasets (11 files)** | Eval harness has ground truth | Eval drop > 2% blocks CI | cross-cut + Batches 1/3/4/5/6/7 | L |
| 6 | **Hierarchical bootstrap CI for benchmarks** | Honest CI under correlated sources | `effective_n ≤ N` always | Batch 5 | M |
| 7 | **Digest Opus budget — checkpointed multi-day** | Never overrun spec budget | 0 overruns | Batch 7 | M |
| 8 | **Cluster service + cross-pillar integration module** | P2/P3/P4 onboard zero-code | DeltaReport for synthetic P2 schema-clean | new services | L |
| 9 | **Graph: 28 spec node types + sharded persistence** | Spec-compliant KG storage | ≥ 22 node kinds; persist/load identical | Batch 2 | L |
| 10 | **SLOs + Cloud Monitoring objects + budget-gated deploys** | Industry-grade reliability discipline | Budget-exhausted deploys blocked | Batch 9 | M |

**Bottom line.** The system runs end-to-end, ships a deploy-ready Cloud Run stack, and passes 319 backend + 45 frontend tests. But to be sold as "industry-grade" the 10 actions above must land — about **14 engineer-days** of work. None require new infrastructure. All are local code changes + golden-dataset curation.

---

## Appendix A — Verdict by spec section, one-liner

§1 Partial · §2 Compliant · §3 Partial (token math fails on digest) · §4 Partial (no leverage tier, no multi-sample, no primary-source dedup, contradiction rules incomplete) · §5 **Defect** (gates wrong) · §6 Partial · §7 Partial · §8 **Partial** (14 of 28 node kinds; in-process only) · §9 Partial · §10 **Defect** (no Firestore-sharded KG persistence) · §11.6 Partial · §11.7 **Defect** (Opus budget) · §11.8 Partial · §11.12 Compliant · §11.15 Partial · §12-§16 Compliant · §17 **Defect** (no SLOs) · §18 Partial · §19 **Defect** (no goldens) · §20-§21 Compliant · §22 **Defect** (ACs not measurable) · §23 Compliant · §24 Partial.

---

## Appendix B — ADR backlog (close out §24)

- ADR-0007 — Cloud DLP custom infoTypes for FS (SSN variants, account numbers, MICR routing).
- ADR-0008 — Leverage tiers: which operations skip which steps of the consultant loop.
- ADR-0009 — Multi-sample policy: n_samples + temperature + seed by leverage tier; non-deterministic regression strategy.
- ADR-0010 — Hierarchical bootstrap rationale + cluster-by-primary-source.
- ADR-0011 — Opus budget vs digest scope: why we picked checkpointed multi-day (or downgrade-to-Sonnet, or quota raise).
- ADR-0012 — Pillar-as-data: enforcement via `import-linter` + synthetic-P2 acceptance test.
- ADR-0013 — Cluster service rationale: K-Means on embeddings vs. graph community detection vs. hierarchical agglomerative; trade-off table.
