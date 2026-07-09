# ZMS Source Authorities

This document names the source authority that backs each ZMS criterion's `source` label. The diagnostic report cites these authorities by name when surfacing findings; this file is what makes those citations defensible. **It is the human-readable counterpart of the `source` and `well_architected_pillar` fields in `data/zms-criteria.json` and must agree with that data exactly.** Every criterion listed here carries the same source label and pillar as the register; the self-test and the alignment check in this skill enforce that agreement.

## The calibration philosophy: quality from a senior SA's point of view

ZMS encodes what a senior Salesforce Solution Architect considers a quality SDD, independent of any one template. A criterion earns its place because an experienced SA would say *"a good SDD addresses this, and an SDD that omits it is weaker and less ready for estimation."* The `source` label records **on whose authority** that judgement rests:

- **Well-Architected**, the requirement is canonical Salesforce guidance, published in the Well-Architected Framework. The finding rests on Salesforce's own authority. Zennify adds no incremental substance to these; the in-house methodology may codify or reference them, but it does not extend them, so claiming Zennify authorship would be over-claiming and would *weaken* the finding.
- **Zennify SDD standard**, genuine in-house IP: requirements that come from the Zennify SDD template's structure, from accumulated senior-SA review patterns across engagements, and from Zennify's delivery quality bar. These do not appear in public Well-Architected guidance. This is the bucket the evaluation most wants to keep complete and to grow, when an off-the-shelf SDD demonstrates one of these and the ZennAgent SDD does not, that is the signal that the Zennify template should expand its IP.
- **Zennify + Well-Architected**, reserved for the case where Zennify *provably* layers an incremental requirement on top of a Well-Architected concept (i.e., the prose below can state exactly what Zennify adds beyond WA). **At the v4.6 freeze this set is empty.** Zennify was found to add no incremental substance on top of Well-Architected anywhere in the register; every criterion that touches WA is canonical WA and is labelled `Well-Architected` alone. The label remains defined so a future version can use it if a genuine incremental-Zennify requirement is authored, but it must never be used as a default for "this is WA and also in our template."

> **Why this matters for the report.** A finding labelled `Well-Architected` cannot be dismissed as a Zennify preference, Salesforce itself requires the depth. A finding labelled `Zennify SDD standard` is honest in-house IP and is exactly where the methodology team can act. Mislabelling canonical Salesforce guidance as a Zennify standard invites the pushback *"that's not yours"* and obscures that Salesforce mandates it, so getting the label right makes every judgement call more grounded, not less.

The evaluation scores each lane independently against this bar. A result in which the ZennAgent SDD is strong everywhere and the off-the-shelf SDD beat it nowhere is a valid result; the report then carries calibration information that enriches the SDD rather than a deficit list. Negative lift is one possible outcome, never a target and never a validity condition.

---

## Source distribution (v4.6, post-alignment; identical to the v4.5/v4.0/1.1.0 freeze)

| Source label | Count | % |
|---|---:|---:|
| Zennify SDD standard | 58 | 59% |
| Well-Architected | 41 | 41% |
| Zennify + Well-Architected | 0 | 0% |
| **Total** | **99** | **100%** |

This distribution is recomputed in `data/zms-criteria.json` → `source_distribution` and surfaces in Diagnostic Report §4. The two-bucket reality (Zennify in-house IP vs. canonical Salesforce guidance) is the honest calibration split: roughly half the quality bar is Salesforce's published standard, roughly half is Zennify's accumulated in-house practice.

---

## Well-Architected (41 criteria)

Salesforce's Well-Architected Framework defines three pillars: **Trusted**, **Easy**, **Adaptable**, published at `architect.salesforce.com/well-architected`. Every criterion in this section is canonical Well-Architected guidance with no incremental Zennify requirement, and carries `source = "Well-Architected"` with the single canonical pillar shown.

### Trusted pillar (17 criteria)

What makes a Salesforce solution secure, compliant, and reliable.

| Criterion | Trusted aspect |
|---|---|
| `3B.org` | Org-level security baseline (OWD, session, password, login IP) |
| `3B.object` | Object-level CRUD via permission sets |
| `3B.field` | Field-level security via permission set (not profile-only) |
| `3B.record` | Record-level access (OWD + named sharing mechanism), *critical floor* |
| `3B.action` | Action / UI-level access constraints per persona |
| `3B.apex` | Programmatic enforcement (with/without sharing, stripInaccessible) |
| `3B.integration_user` | Integration user with least-privilege permission set |
| `3B.external_user_exposure` | Experience Cloud external surface bounded, *critical floor* |
| `3B.encryption_shield` | Shield / encryption where data sensitivity requires |
| `3B.auditability` | FieldHistory / Shield Event Monitoring for audit needs |
| `3B.data_retention` | Retention / archival policy |
| `3B.regulatory_control_mapping` | Each cited regulation mapped to a concrete control |
| `1C.regulatory_citation` | Applicable regulations for the vertical named |
| `2B.security_nfr` | Security NFR addressed via a named Salesforce mechanism |
| `2B.compliance` | Compliance NFR addressed via a named Salesforce mechanism |
| `3E.identity_federation` | Identity / SSO across clouds addressed |
| `4A.security_sharing_model` | Holistic security & sharing coverage, *critical floor* |

The six-layer security stack (Org, Object, Field, Record, Action, Apex) is the canonical Well-Architected Trusted decomposition.

### Easy pillar (10 criteria)

What makes a Salesforce solution maintainable, admin-friendly, and aligned to platform conventions.

| Criterion | Easy aspect |
|---|---|
| `3A.cloud_products` | Specific clouds, products, and core data-model approach named |
| `3A.platform_native_first` | Platform-native capability preferred over custom, justified |
| `3C.declarative_first` | Declarative-first approach (Flow before Apex) |
| `3C.execution_context` | Automation execution context / order-of-execution addressed |
| `3C.bulk_behavior` | Automation designed bulk-safe (no DML/SOQL in loops) |
| `3C.recursion_control` | Recursion / re-entry guard named |
| `3C.transaction_boundaries` | Sync vs async and transaction boundaries decided |
| `3C.error_handling` | Error / fault handling designed for automation |
| `3C.testability` | Test / coverage approach stated for custom work |
| `3C.dynamic_forms` | Dynamic Forms / Dynamic Actions over static layouts |

These criteria reward platform-aligned choices and penalise patterns that increase maintenance burden.

### Adaptable pillar (14 criteria)

What makes a Salesforce solution upgrade-safe, configurable, scalable, and resilient to change.

| Criterion | Adaptable aspect |
|---|---|
| `3D.separation_of_concerns` | Apex concerns separated (handler / service / selector) |
| `3D.custom_metadata_config` | Variable config externalised to Custom Metadata Type |
| `3D.trigger_framework` | One-trigger-per-object / framework pattern |
| `3D.platform_events` | Platform Events / CDC where async decoupling is warranted |
| `3D.upgrade_safe_patterns` | Patterns chosen to survive package/platform upgrades |
| `3D.api_versioning` | API versions pinned and version strategy stated |
| `3D.platform_error_handling` | Integration error strategy (retry / dead-letter / monitoring) |
| `3E.cross_cloud_data_flow` | Data flow across clouds named with mechanism |
| `5A.api_version_auth_sla` | Per integration: API version, auth model, SLA stated |
| `5C.idempotency` | Idempotency / duplicate-handling per integration |
| `1C.volume` | Data volumes / LDV surfaced (migration volume, integration frequency) |
| `2B.performance` | Performance NFR addressed via a named Salesforce mechanism |
| `2B.scalability` | Scalability NFR addressed via a named Salesforce mechanism |
| `3C.async_volume_strategy` | Async processing (Batch/Queueable/Scheduled) chosen when volume warrants |

These criteria reward patterns that survive Salesforce releases and scale with data and load.

---

## Zennify SDD standard (58 criteria)

Genuine in-house IP, requirements that do not appear in public Well-Architected guidance. These trace to three origins. All carry `source = "Zennify SDD standard"` with `well_architected_pillar = null`. **The evaluation treats this bucket as the place where Zennify IP can be measured and grown:** when an off-the-shelf SDD demonstrates one of these and the ZennAgent SDD omits it, the senior-SA judgement is that the Zennify template should add it.

### Template-driven requirements

The Zennify SDD template embeds specific design depths that the in-house methodology has found necessary for delivery success and for a concrete hand-off to estimation:

- Capability decomposition with feature-level breakdown (`4A.capability_modules`, `4A.config_table`)
- Document overview / orientation surface (`4A.document_overview`)
- Story coverage summary as an auditable surface (`4A.user_story_coverage`)
- Data model, record types, and Lightning page design as named structural components (`4A.data_model`, `4A.record_types`, `4A.lightning_pages`)
- Integration and data-migration design as explicit components (`4A.integration_design`, `4A.data_migration_design`)
- Out-of-scope callouts per module with named excluded alternatives (`6A.out_of_scope_callout`, `6A.exclusion_specificity`, `6A.scope_boundary_table`)
- Scope boundary alignment to the BRD Deliverables table (`7C.boundary_alignment`)
- Field Mapping table with Source / Source System / Target / Transformation Notes (`5C.field_mapping`)
- Reporting and analytics design, report types, key reports/dashboards, analytics audience (`4A.reporting_analytics`)
- Business process flows, each in-scope process described trigger-to-outcome with responsible persona/system (`4A.business_process_flows`)
- Open decisions log, unresolved decisions surfaced with owner and impact (`4A.open_decisions_log`)
- Confidence annotations, provisional design elements marked, tied to specific sections (`4A.confidence_annotations`)

These criteria measure substance, the template is the mechanism by which the substance is elicited, but the criterion does not require the template's layout. An SDD that delivers the substance in a different layout still scores Present.

### Senior-SA review patterns

Criteria distilled from accumulated SA review experience across Zennify engagements. They reflect what Zennify SAs have learned to look for and do not appear in public Well-Architected guidance:

- Requirement → object / field resolution with API naming (`1A.object`, `1A.field`)
- Story / acceptance-criterion → named Salesforce mechanism mapping (`1A.sf_mechanism_named`, `1A.ac_to_mechanism`)
- Persona → capability / license / Lightning page / record-visibility explicit mapping (`1B.persona_capability`, `1B.persona_license`, `1B.persona_lightning_page`, `1B.persona_record_visibility`)
- License fit and multi-cloud license optimisation (`3A.license_fit`, `3E.license_optimisation`)
- Naming discipline: SF mechanism named for automation, AD numbering convention (`3C.sf_mechanism_named`, `3C.design_standards_naming`)
- Architectural decisions per major capability, with decision / rationale / options / trade-offs (`4B.ad_per_module`, `4B.decision`, `4B.rationale`, `4B.options_context`, `4B.trade_offs`)
- Simpler / safer alternative evaluation for Complex items, with rationale for not choosing it (`4B.simpler_alternative`)
- Cross-module dependencies, named systems, and integration pattern frequency (`5A.cross_module_dependencies`, `5A.named_systems`, `5A.pattern_frequency`)
- Per-integration architectural decision, retry/fallback design (`5C.integration_ad`, `5C.retry_fallback`)
- Estimation-readiness: feature decomposition and mechanism specificity that enables scope-item mapping (`7A.feature_decomposition`, `7A.mechanism_enables_mapping`)
- Complexity rating and complex-item risk flagging (`7B.complexity_rating`, `7B.complex_risk_flag`)
- Data migration AD for tooling and External ID strategy (`7C.migration_external_id_ad`)

### Quality-bar enforcement

Criteria that codify standards baked into Zennify's delivery practice and set the floor for what Zennify considers SOW-ready:

- Story coverage complete, with coverage flag (`2A.story_coverage_complete`, *critical floor*, `2A.coverage_flag`)
- Complex-item risk, gap, and risk identification (`2C.complex_flagged_risk`, `2C.gap_id`, `2C.risk_id`)
- Quantified limits surfaced (`1C.quantified_limits`)
- Material assumptions stated explicitly and testably; assumed-in-place items called out (`5B.assumptions_explicit`, `5B.assumed_inplace`)
- Coverage complete before SOW hand-off; no future-phase creep (`6B.coverage_before_handoff`, `6B.no_future_phase_creep`)
- Context-not-contractual discipline; no unrequested build (`6C.context_not_contractual`, `6C.no_unrequested_build`)
- Capability modules and data model as critical structural floors (`4A.capability_modules`, *critical floor*, `4A.data_model`, *critical floor*, `4A.user_story_coverage`, *critical floor*, `4A.security_sharing_model` is Trusted/WA and listed above)

An SDD that misses these is a delivery risk regardless of how strong it is elsewhere.

---

## Zennify + Well-Architected (0 criteria at the v4.6 freeze)

Reserved for criteria where Zennify provably layers an incremental requirement on top of a Well-Architected concept. **Empty at the v4.6 freeze:** the alignment review found that Zennify adds no incremental substance on top of Well-Architected anywhere in the current register. Where the in-house methodology references a WA concept, it does so without extending it, so the criterion is labelled `Well-Architected` alone.

If a future version authors a genuine incremental-Zennify requirement on a WA concept, it may use this label, but only with prose here stating exactly what Zennify adds beyond the WA baseline. The label must never be used as a default for "this is Well-Architected and also lives in our template."

---

## How the report cites authorities

The diagnostic report's §7 actions cite the source label per criterion. Two illustrative shapes:

**Canonical Salesforce guidance (Well-Architected):**

> *"`3B.record` (Well-Architected, Trusted, Critical): SDD §3.4 states 'OWD set to Private; sharing handled appropriately', names OWD but no specific sharing mechanism. Authority: Salesforce Well-Architected, Trusted pillar (record-level access requires OWD + a named sharing mechanism). Required: name the specific sharing mechanism, criteria-based rule, manual share, Apex managed, or team-based, with the field driving the share and the user group receiving access. Where: Security & Sharing Model component."*

This rests on Salesforce's own authority and cannot be dismissed as a Zennify preference.

**In-house IP (Zennify SDD standard):**

> *"`4B.simpler_alternative` (Zennify SDD standard, High): the off-the-shelf SDD evaluated a declarative alternative to the proposed Apex trigger at §4.3 and stated why it was not chosen; the ZennAgent SDD selected Apex without evaluating a simpler path. Authority: Zennify SA review pattern (Complex items must show a simpler/safer alternative was considered, with rationale for rejecting it). Required: for each Complex item, document the declarative/OOTB alternative considered and the reason it was not selected. Where: Architectural Decisions per module. This is a candidate for Zennify template IP expansion, a strong off-the-shelf SDD surfaced it and the template did not prompt for it."*

This is honest in-house IP, and the off-the-shelf contrast makes it an actionable IP-expansion target for the methodology team.

---

*Source authority document v4.6 (aligned; +5 criteria over v1.0.1: 4A reporting/process/open-decisions/confidence + 3C async-volume). Updated synchronously with every criterion source/pillar change in `data/zms-criteria.json`. Last aligned: B1 re-attribution, 42 joint criteria resolved to 40 Well-Architected + 2 Zennify SDD standard; `Zennify + Well-Architected` reduced to empty; `4A.security_sharing_model` pillar corrected Easy→Trusted; `1A.sf_mechanism_named` confirmed Zennify-pure (removed from WA Easy listing).*
