# Section D slice: Dims 4-7 (read in sub-batches 4b and 4d ONLY)

### Bundle keys for this slice (emit EXACTLY these snake_case keys at assembly)

| ID | Sub-criterion | Bundle key (`dim_N_sub_criteria` + top-level `content_coding`) |
|---|---|---|
| 4A | Component presence | `component_presence` |
| 4B | Architectural decision quality | `architectural_decision_quality` |
| 5A | Dependency ID/classification | `dependency_id_classification` |
| 5B | Assumption documentation | `assumption_documentation` |
| 5C | Integration failure modes | `integration_failure_modes` |
| 6A | In/out delineation | `in_out_delineation` |
| 6B | Phasing/prioritisation | `phasing_prioritisation` |
| 6C | Scope-creep resistance | `scope_creep_resistance` |
| 7A | Estimable work units | `estimable_work_units` |
| 7B | Complexity/effort indicators | `complexity_effort_indicators` |
| 7C | Delivery readiness | `delivery_readiness_signals` |

### Category sets per dimension (the fixed code frame, ZMS v4.6)

The 22 sub-criteria are each calibrated by their mapped ZMS criteria. The mapping is canonical at the ZMS v4.6 freeze and lives in `zms-22-mapping.json`. Counts by sub-criterion (99 ZMS criteria → 22 parents):
| Sub-criterion | ZMS criteria count | Examples (full list in zms-22-mapping.json) |
|---|---:|---|
| 4A Component presence | 10 | `4A.capability_modules` (critical), `4A.data_model` (critical), `4A.user_story_coverage` (critical), `4A.security_sharing_model` (critical), `4A.config_table`, `4A.record_types`, `4A.document_overview`, etc. |
| 4B ADQ | 6 | `4B.decision`, `4B.rationale`, `4B.options_context`, `4B.trade_offs`, `4B.ad_per_module`, `4B.simpler_alternative` |
| 5A Dependency ID | 4 | `5A.named_systems`, `5A.api_version_auth_sla`, `5A.cross_module_dependencies`, `5A.pattern_frequency` |
| 5B Assumptions | 2 | `5B.assumptions_explicit`, `5B.assumed_inplace` |
| 5C Failure modes | 4 | `5C.retry_fallback`, `5C.idempotency`, `5C.field_mapping`, `5C.integration_ad` |
| 6A In/out | 3 | `6A.scope_boundary_table`, `6A.out_of_scope_callout`, `6A.exclusion_specificity` |
| 6B Phasing | 2 | `6B.no_future_phase_creep`, `6B.coverage_before_handoff` |
| 6C Creep resistance | 2 | `6C.in_scope_only`, `6C.no_speculative_features` |
| 7A Work units | 2 | `7A.feature_decomposition`, `7A.mechanism_enables_mapping` |
| 7B Complexity | 2 | `7B.complexity_rating`, `7B.complex_risk_flag` |
| 7C Delivery readiness | 2 | `7C.boundary_alignment`, `7C.migration_external_id_ad` |

## Dim 4 floor (rubric §6.4.1 / OH §3.5.2)

Apply `content_mapping.dim_4_floor_cap` to each pass's Dim 4: `null` (no floor) | `10` (1 Stub/Missing) | `7` (2+).

## Integration-heavy weight swap (rubric §2)

If `run_integration_heavy = true`, swap Dim 5 and Dim 7 weights. Dim 5 becomes max 15 (threshold 12.0); Dim 7 becomes max 10 (threshold 8.0).

## Multi-cloud sub-criterion (rubric §6.3)

If `multi_cloud = true` (from applicability flags; `salesforce_clouds` contains `+` per intake derivation), Dim 3 has 5 sub-criteria each out of 4 (cap 20). Otherwise 4 sub-criteria each out of 5 (cap 20). Set `dim_3_sub_criteria.multi_cloud_architecture` to `null` in single-cloud case. ZMS criteria with `applicability: MULTI_CLOUD` (the three `3E.*` criteria) fire only in this case.

### Dim 4: Design Specificity (max 15)

**4A Component Presence (max 9)**
Score = (count of Substantive components / 8) × 9, then apply judgment:
- **9:** All 8 required components Substantive with mechanism-level naming throughout (objects, fields, Flows, Apex classes, LWCs, integration patterns, not just product names).
- **7-8:** All 8 present (all Substantive or 1 borderline). Mechanism-level naming on most.
- **5-6:** 7 components present (1 Missing or Stub). Module-level naming (e.g., "Sales Cloud opportunity management" rather than "Opportunity.StageName").
- **3-4:** 6 components present. Product-level naming dominant.
- **1-2:** 5 or fewer components present.
- **0:** No recognisable components.

**4B Architectural Decision Quality (max 6)**
- **6:** ≥4 ADRs with all 5 elements (Decision + Context + Options + Rationale + Trade-offs). All 6 canonical SF trade-offs addressed where relevant. Trade-offs quantified.
- **5:** 3-4 ADRs with most elements. Most relevant canonical trade-offs addressed.
- **4:** 2-3 ADRs with Decision + Rationale. Some trade-offs mentioned.
- **3:** 1-2 ADRs. Decisions stated without full rationale or alternatives.
- **2:** Design decisions mentioned in prose without ADR structure.
- **1:** "We chose Salesforce" type statements. No design reasoning.
- **0:** No design decisions documented.

### Dim 5: Dependencies and Assumptions (max 10 base / 15 int-heavy)

**5A Dependency ID and Classification (max 4 base / 6 int-heavy)**
- **4/6:** All 6 dependency categories addressed (data, integration, identity/auth, infrastructure, third-party, operational). Named systems with API versions, auth mechanisms (Named Credentials, OAuth flows), SLAs, criticality ratings.
- **3/5:** 5 categories addressed. Most systems named with auth mechanisms.
- **2/3-4:** 3-4 categories. Systems named without API versions or auth details.
- **1/2:** Generic dependency list. Systems named without classification.
- **0/0-1:** Dependencies omitted or fundamentally wrong.

**5B Assumption Documentation (max 3 base / 4 int-heavy)**
- **3/4:** Numbered assumptions with: validation plan, owner, consequence if wrong, timeline. Each assumption traceable to a design decision.
- **2/3:** Assumptions listed with owners. Some validation plans. Consequences mentioned for critical ones.
- **1/2:** Assumptions listed without owners, validation plans, or consequences.
- **0/0-1:** No assumptions documented or assumptions trivialised.

**5C Integration Failure Modes (max 3 base / 5 int-heavy)**
- **3/5:** Per-integration: success path, failure with retry strategy (exponential backoff, circuit breaker), dead-letter queue via platform events, monitoring and alerting (custom objects or Event Monitoring), idempotency guarantees.
- **2/3-4:** Most integrations with error handling and retry. Some monitoring. Idempotency mentioned.
- **1/2:** Generic error handling ("retry on failure") without per-integration design.
- **0/0-1:** No error handling on any integration (→ TRUST-007).

### Dim 6: Scope Discipline (max 10)

**6A In/Out Delineation (max 4)**
- **4:** Explicit in-scope/out-of-scope table with per-story binding and exclusion rationale. Every in-scope item traceable to a BRD requirement.
- **3:** Scope table present. Most items tied to stories. 1-2 items without explicit BRD tracing.
- **2:** Scope described narratively. Some items tied to BRD. No table format.
- **1:** Scope mentioned in passing. No structured delineation.
- **0:** No scope definition or scope contradicts BRD.

**6B Phasing and Prioritisation (max 3)**
- **3:** Phases with story-to-phase mapping, go-live criteria per phase, and priority rationale linked to BRD objectives.
- **2:** Phases defined with some story mapping. Go-live criteria mentioned generically.
- **1:** Phasing mentioned but not structured with story mapping.
- **0:** No phasing.

**6C Scope Creep Resistance (max 3)**
- **3:** Requirements interpreted faithfully. No features designed that are not in the BRD. Every design element traces to a BRD requirement.
- **2:** Mostly faithful. 1-2 minor additions that could be justified as implied requirements.
- **1:** Several additions beyond BRD scope without explicit justification.
- **0:** Significant scope creep features designed that contradict or go well beyond BRD.

### Dim 7: Estimation Readiness (max 15 base / 10 int-heavy)

**7A Estimable Work Units (max 5 base / 3 int-heavy)**
- **5/3:** Every design element → discrete work item. Build vs configure distinguished for each. Mechanism named for sizing (e.g., "Custom object with 12 fields, configure; Apex trigger with batch, build").
- **4/2:** Most items decomposed. Build vs configure distinguished for most. Some items need clarification.
- **3/2:** Some items decomposed. Build vs config noted generically.
- **2/1:** High-level work breakdown without mechanism-level detail.
- **1/0:** Feature-level only. Cannot estimate without significant discovery.

**7B Complexity and Effort Indicators (max 5 base / 4 int-heavy)**
- **5/4:** Every item with complexity driver (Simple/Moderate/Complex) and basis. Data volume, process complexity, integration count, customisation depth all quantified.
- **4/3:** Most items with complexity drivers. Key volumes quantified.
- **3/2:** Some complexity indicators. Volumes mentioned without quantification.
- **2/1:** Generic complexity statements ("this is complex").
- **1/0:** No complexity analysis.

**7C Delivery Readiness Signals (max 5 base / 3 int-heavy)**
- **5/3:** Deployment strategy (change sets, DevOps Center, CI/CD), environment plan (sandbox strategy), testing approach (unit, integration, UAT with SF-specific tools), data migration scope, cross-team dependency surface.
- **4/2:** Most delivery elements present. 1-2 areas missing detail.
- **3/2:** Some delivery elements. Testing approach mentioned generically.
- **2/1:** Brief deployment mention. No testing or environment strategy.
- **1/0:** No delivery readiness information.
