# Section D slice: Dims 1-3 (read in sub-batches 4a and 4c ONLY)

### Bundle keys for this slice (emit EXACTLY these snake_case keys at assembly)

| ID | Sub-criterion | Bundle key (`dim_N_sub_criteria` + top-level `content_coding`) |
|---|---|---|
| 1A | Requirement parsing depth | `requirement_parsing_depth` |
| 1B | Persona recognition | `stakeholder_persona_recognition` |
| 1C | Constraint extraction | `constraint_assumption_extraction` |
| 2A | Functional traceability | `functional_requirement_traceability` |
| 2B | NFR coverage | `nfr_coverage` |
| 2C | Gap/risk | `gap_risk_identification` |
| 3A | Cloud/module | `cloud_module_selection` |
| 3B | Trusted | `trusted_design` |
| 3C | Easy | `easy_design` |
| 3D | Adaptable | `adaptable_design` |
| 3E | Multi-cloud | `multi_cloud_architecture` (set to `null` when single-cloud) |

### Category sets per dimension (the fixed code frame, ZMS v4.6)

The 22 sub-criteria are each calibrated by their mapped ZMS criteria. The mapping is canonical at the ZMS v4.6 freeze and lives in `zms-22-mapping.json`. Counts by sub-criterion (99 ZMS criteria → 22 parents):
| Sub-criterion | ZMS criteria count | Examples (full list in zms-22-mapping.json) |
|---|---:|---|
| 1A Requirement parsing depth | 4 | `1A.object`, `1A.field`, `1A.sf_mechanism_named`, `1A.ac_to_mechanism` |
| 1B Persona recognition | 4 | `1B.persona_capability`, `1B.persona_record_visibility`, etc. |
| 1C Constraint extraction | 3 | `1C.volume`, `1C.quantified_limits`, `1C.regulatory_citations` |
| 2A Functional traceability | 2 | `2A.story_coverage_complete` (critical), `2A.coverage_flag` |
| 2B NFR coverage | 4 | `2B.performance`, `2B.security_nfr`, `2B.scalability`, `2B.compliance` |
| 2C Gap/risk | 3 | `2C.gap_id`, `2C.risk_id`, `2C.complex_flagged_risk` |
| 3A Cloud/module | 3 | `3A.cloud_products`, `3A.platform_native_first`, `3A.license_fit` |
| 3B Trusted (6+layer security) | 12 | `3B.org`, `3B.object`, `3B.field`, `3B.record` (critical), `3B.action`, `3B.apex`, `3B.integration_user`, `3B.external_user_exposure` (critical, EXTERNAL_USERS), `3B.auditability`, `3B.encryption_shield`, `3B.data_retention`, `3B.regulatory_control_mapping` |
| 3C Easy | 10 | `3C.declarative_first`, `3C.bulk_behavior`, `3C.execution_context`, `3C.error_handling`, `3C.transaction_boundaries`, `3C.recursion_control`, `3C.sf_mechanism_named`, `3C.design_standards_naming`, `3C.dynamic_forms`, `3C.testability` |
| 3D Adaptable | 6 | `3D.platform_error_handling`, `3D.separation_of_concerns`, `3D.custom_metadata_config`, `3D.api_versioning`, `3D.platform_events`, `3D.trigger_framework`, `3D.upgrade_safe_patterns` |
| 3E Multi-cloud | 3 | `3E.cross_cloud_data_flow`, `3E.identity_federation`, `3E.license_optimisation` (MULTI_CLOUD only) |

## Deductions on Dim 3

Apply after sub-criterion scoring (rubric §7.1, §7.2 + OH §3.6.4):

1. Raw subtotal = sum of Dim 3 sub-criterion scores, capped at 20.
2. Trust deductions per OH §3.6.4 with severity tiers (refinement P2-C):
   - **Critical (blocks deployment):** TRUST-002 (no security model, -5), TRUST-008 (governor violations, -5), TRUST-009 (hardcoded credentials, -5)
   - **Major (requires rework):** TRUST-001 (Workflow Rules, -3), TRUST-005 (Session ID, -3), TRUST-007 (no error handling, -3)
   - **Minor (best practice deviation):** TRUST-003 (Classic UI, -1), TRUST-004 (without sharing, -1), TRUST-006 (legacy Connected Apps, -1)
   No cumulative cap on Trust; Dim 3 floors at zero. Severity tier surfaces in the Diagnostic Report's Prioritised SA Review List (report §3 / Appendix A).
3. Release-awareness deductions taken from THIS LANE'S release-awareness findings only (never re-research mid-scoring): apply each finding's `rr_deduction` as emitted, citing its `finding_id` via `release_finding_ref`. Under the binary RR model the emitted RR values are −3 for any confirmed-not-in-force status (retired/end_of_support/superseded) and −1 for `in_force_unverified` when the live path ran (0 otherwise). Cumulative RR cap −9 per rubric §7.2.
4. Final Dim 3 = `max(0, raw_subtotal + capped_rr + trust_total)`.

Deductions are deterministic, same SDD content triggers the same deductions every pass.

### Dim 1: BRD Comprehension (max 15)

**1A Requirement Parsing Depth (max 5)**
- **5:** Every user story decomposed to object + field + automation + AC-to-SF-mechanism mapping. Each AC tied to a specific configuration or code element.
- **4:** Most stories decomposed to object + automation level. ACs referenced but not all mapped to mechanisms.
- **3:** Stories decomposed to feature level (e.g., "lead management" rather than "Lead.Status picklist with validation rule"). Some SF mechanisms named.
- **2:** Stories paraphrased with SF product mentions (e.g., "Sales Cloud will handle leads") but no mechanism decomposition.
- **1:** Stories acknowledged or listed but not decomposed. No SF-specific interpretation.
- **0:** Stories ignored or fundamentally misstated.

**1B Stakeholder and Persona Recognition (max 5)**
- **5:** Each persona → license type + Permission Set Group + role hierarchy position + Lightning App / page layout. Persona-to-capability matrix present.
- **4:** Each persona → license type + role hierarchy. Most PSGs identified. No explicit capability matrix.
- **3:** Personas named with general role descriptions. License types mentioned for some. No PSG or role hierarchy mapping.
- **2:** Users referenced as groups ("sales team", "managers") without individual persona breakdown.
- **1:** Users mentioned in passing. No persona analysis.
- **0:** No user/persona consideration.

**1C Constraint and Assumption Extraction (max 5)**
- **5:** Constraints quantified: record counts with LDV thresholds, regulatory citations (e.g., "SOX §302 requires audit trail"), governor limit implications calculated (e.g., "150 SOQL queries per transaction allows 3 per trigger in a 50-object batch").
- **4:** Constraints identified with platform awareness (e.g., "high volume, consider Big Objects") but not fully quantified.
- **3:** Constraints at category level ("high volume", "regulatory requirements") without quantification or SF mechanism linkage.
- **2:** Constraints mentioned in passing without categorisation or quantification.
- **1:** One or two constraints acknowledged without analysis.
- **0:** No constraints identified.

### Dim 2: Requirement Coverage (max 15)

**2A Functional Requirement Traceability (max 5)**
- **5:** Traceability matrix present. Every story/AC → design decision or explicit out-of-scope rationale. Coverage is verifiable by inspection.
- **4:** All in-scope requirements addressed with traceable references. No matrix but inline story-ID citations. ≤1 minor gap.
- **3:** Most requirements addressed. 1-2 minor omissions. Partial traceability (some story IDs cited, some not).
- **2:** Several requirements addressed at feature level without specific story traceability.
- **1:** Requirements acknowledged as a group ("the BRD requirements will be addressed") without per-requirement response.
- **0:** Requirements ignored or silently omitted.

**2B Non-Functional Requirement Coverage (max 5)**
- **5:** Every NFR addressed with a named SF mechanism: SOQL optimisation for performance, Shield encryption for compliance, platform events for async, Big Objects for LDV. Quantified where applicable.
- **4:** Most NFRs addressed with SF mechanisms. 1-2 at category level.
- **3:** NFRs at category level ("performance will be addressed") without specific SF mechanisms.
- **2:** NFRs mentioned in a general section without per-requirement treatment.
- **1:** NFRs acknowledged in passing.
- **0:** NFRs absent.

**2C Gap and Risk Identification (max 5)**
- **5:** Open Decisions Log with: decision description, owner, deadline, impact if unresolved, status. Deferred items with rationale. Risks with mitigation strategy and probability/impact rating.
- **4:** Gaps and risks identified with owners. Most have mitigation. No formal ODL but equivalent coverage.
- **3:** Some gaps identified. Risks mentioned without mitigation or ownership.
- **2:** A general "risks and assumptions" section with high-level statements.
- **1:** One or two risks mentioned in passing.
- **0:** No gap, risk, or assumption identification.

### Dim 3: Salesforce Solution Fit (max 20)

Scored per sub-criterion using the rubric §6.3 band criteria. Behavioural anchors align with the Well-Architected pillar priority (Trusted > Easy > Adaptable):

**3A Cloud and Module Selection (max 5 single / 4 multi)**
- **5/4:** Correct clouds and editions for every use case. Platform-native features prioritised over AppExchange. License implications analysed per persona. Edition feature boundaries identified.
- **4/3:** Correct clouds selected. Most features platform-native. License types mentioned but not analysed per persona.
- **3/2:** Correct primary cloud. Some features from wrong module or edition. License type acknowledged generically.
- **2/1:** Cloud named but features not matched to use case. No license analysis.
- **1/0:** Wrong cloud selected or cloud not specified.

**3B Trusted Design (max 5/4), Six-layer security assessed**
- **5/4:** All six security layers addressed explicitly (Org, Object, Field, Record, Action, Apex). Compliance architecture with named mechanisms (Shield, Event Monitoring). Recovery/backup strategy.
- **4/3:** 5 of 6 layers addressed. Compliance mentioned with some mechanisms.
- **3/2:** 3-4 layers addressed. Security model present but incomplete. No compliance mechanisms named.
- **2/1:** Generic security statement. 1-2 layers mentioned. No OWD or sharing model.
- **1/0:** Security not addressed or fundamentally wrong (e.g., all objects Public Read/Write).

**3C Easy Design (max 5/4), Declarative-first assessed**
- **5/4:** Flow-first automation with explicit Apex justification for exceptions. Dynamic Forms. Naming conventions documented. Automation tool selection rationale for each process.
- **4/3:** Declarative-first generally followed. Most automations via Flow. 1-2 unjustified Apex choices.
- **3/2:** Mix of declarative and code without clear rationale. Some automation via Workflow Rules or Process Builder.
- **2/1:** Apex-heavy without justification. No declarative-first consideration.
- **1/0:** Anti-patterns dominant (Workflow Rules for new development → TRUST-001).

**3D Adaptable Design (max 5/4)**
- **5/4:** Custom metadata for configuration. Trigger framework (one trigger per object). Platform Events for async. Upgrade-safe patterns. Namespace considerations.
- **4/3:** Most adaptability patterns present. Custom metadata used. No explicit trigger framework.
- **3/2:** Some configuration externalised. No trigger framework or platform events.
- **2/1:** Hardcoded configuration. No adaptability consideration.
- **1/0:** Architecture would break on platform upgrade.

**3E Multi-Cloud Architecture (max 4, only when multi_cloud=true)**
- **4:** Cross-cloud data flows mapped with identity federation. Reverse flows designed. Cross-cloud licensing optimised.
- **3:** Cross-cloud handoffs designed. Identity federation mentioned. Some flows unmapped.
- **2:** Clouds mentioned as separate workstreams. No cross-cloud integration design.
- **1:** Multi-cloud acknowledged but not designed.
- **0:** Multi-cloud requirement ignored.
