# ZMS Criteria Register

*Version 1.0.0 · Frozen 2026-06-03T13:58:52+00:00 · 99 criteria across 7 dimensions / 22 sub-criteria*

Each criterion measures **substantive content** in the SDD. None reference template format, section number, or methodology marker. The depth_indicator describes what good content contains; the components list the specific things to search for; the source label names the authority that requires it.

**Source labels**
- `Zennify SDD standard`, in-house Zennify methodology
- `Well-Architected`, Salesforce Well-Architected Framework (Trusted / Easy / Adaptable)
- `Zennify + Well-Architected`, reserved for a genuine incremental-Zennify requirement layered on a Well-Architected concept (empty at the v4.6 freeze)

**Markers**
- **†** Critical-floor item, Absent on an applicable engagement caps the parent sub-criterion below the 80% gate
- **★** Beyond template the Zennify SDD template does not explicitly elicit this depth. Independent of the `source` label: a criterion can be canonical Well-Architected **and** beyond the template. These criteria are the prime IP-expansion candidates, Salesforce (or Zennify practice) requires the depth, but the template does not prompt for it, so a ZennAgent SDD may omit it even where an off-the-shelf SDD includes it.

---

## Source distribution

- **Zennify SDD standard**: 58 criteria (in-house IP)
- **Well-Architected**: 41 criteria (canonical Salesforce guidance)
- **Zennify + Well-Architected**: 0 criteria (reserved; empty at the v4.6 freeze, Zennify adds no incremental substance on top of Well-Architected)

## Critical-floor items (7)

These criteria fire the floor cap when Absent on an applicable engagement:

- `2A.story_coverage_complete`, Every story covered (Zennify SDD standard)
- `3B.record`, Record access / sharing (Well-Architected)
- `3B.external_user_exposure`, External-user exposure (Well-Architected)
- `4A.capability_modules`, Capability decomposition (Zennify SDD standard)
- `4A.data_model`, Data model specificity (Zennify SDD standard)
- `4A.user_story_coverage`, Story coverage summary (Zennify SDD standard)
- `4A.security_sharing_model`, Holistic security & sharing coverage (Well-Architected)

---

## Dimension 1: BRD Comprehension

### 1A: Requirement parsing depth

#### `1A.object`: Requirement -> object

- **Depth indicator:** Each capability's business objective resolves to one or more named Salesforce objects (standard or custom; identified by API name where new)
- **Components to search for:**
  - named Salesforce object (standard or custom)
  - API name provided for custom objects
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `ALL`

#### `1A.field`: Requirement -> field

- **Depth indicator:** Requirements resolve to specific field extensions with type and stated purpose
- **Components to search for:**
  - field extension named
  - field type specified
  - stated purpose for each field
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `ALL`

#### `1A.sf_mechanism_named`: Requirement -> named SF mechanism

- **Depth indicator:** SF Mechanism names the actual feature (Scheduled Flow, Approval Process...), never 'automation'/'configuration'
- **Components to search for:**
  - named Salesforce feature (Flow / Approval Process / Validation Rule / Apex / etc.)
  - not vague placeholder ('automation' / 'configuration')
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `ALL`

#### `1A.ac_to_mechanism`: AC -> design element **★**

- **Depth indicator:** Each acceptance criterion is traceable to a design element
- **Components to search for:**
  - traceable to a design element
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `ALL`

### 1B: Stakeholder / persona recognition

#### `1B.persona_capability`: Persona -> capability

- **Depth indicator:** Personas are tied to the capabilities they interact with
- **Components to search for:**
  - personas are tied to the capabilities they interact with
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `ALL`

#### `1B.persona_license`: Persona -> license fit **★**

- **Depth indicator:** Each persona mapped to a Salesforce license type; license fit affects solution viability
- **Components to search for:**
  - each persona mapped to a Salesforce license type
  - license fit affects solution viability
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `ALL`

#### `1B.persona_lightning_page`: Persona -> Lightning page

- **Depth indicator:** Personas are mapped to specific Lightning pages or UI experiences they use
- **Components to search for:**
  - personas are mapped to specific Lightning pages or UI experiences they use
- **Source:** Zennify SDD standard
- **Severity if absent:** Medium
- **Applies:** `UI_IN_SCOPE`

#### `1B.persona_record_visibility`: Persona -> record visibility **★**

- **Depth indicator:** Each persona's record visibility (which records they can see / edit) is explicitly mapped to the technical sharing model
- **Components to search for:**
  - each persona's record visibility scope identified
  - visibility tied to the technical sharing model (OWD + sharing mechanism)
- **Source:** Zennify SDD standard
- **Severity if absent:** Medium
- **Applies:** `ALL`

### 1C: Constraint / assumption extraction

#### `1C.volume`: Volume / LDV

- **Depth indicator:** Data volumes surfaced (migration Est. Volume, integration frequency)
- **Components to search for:**
  - data volume surfaced (migration estimated volume)
  - integration frequency surfaced where applicable
- **Source:** Well-Architected (Adaptable pillar)
- **Severity if absent:** High
- **Applies:** `ALL`

#### `1C.regulatory_citation`: Regulatory citations **★**

- **Depth indicator:** Named regulations for the vertical surfaced
- **Components to search for:**
  - named regulations for the vertical surfaced
- **Source:** Well-Architected (Trusted pillar)
- **Severity if absent:** High
- **Applies:** `REGULATORY_CITATION`

#### `1C.quantified_limits`: Quantified limits **★**

- **Depth indicator:** Other quantified constraints (SLA, retention) captured
- **Components to search for:**
  - other quantified constraints (SLA, retention) captured
- **Source:** Zennify SDD standard
- **Severity if absent:** Medium
- **Applies:** `ALL`

---

## Dimension 2: Requirement Coverage

### 2A: Functional requirement traceability

#### `2A.story_coverage_complete`: Every story covered **†**

- **Depth indicator:** Every BRD user story has at least one design element addressing it, is deferred with a stated reason, or is explicitly excluded
- **Components to search for:**
  - every BRD user story has at least one design element addressing it
  - OR the story is deferred with a stated reason
  - OR the story is explicitly excluded
- **Source:** Zennify SDD standard
- **Severity if absent:** Critical
- **Applies:** `ALL`

#### `2A.coverage_flag`: Covered / not-covered flag

- **Depth indicator:** Each story shows an explicit covered / not-covered flag
- **Components to search for:**
  - each story carries a covered / not-covered flag
  - the flag is auditable at a glance
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `ALL`

### 2B: NFR coverage

#### `2B.performance`: Performance NFR **★**

- **Depth indicator:** Performance NFR addressed with a named SF mechanism
- **Components to search for:**
  - performance NFR addressed
  - addressed via a named Salesforce mechanism
- **Source:** Well-Architected (Adaptable pillar)
- **Severity if absent:** High
- **Applies:** `ALL`

#### `2B.security_nfr`: Security NFR **★**

- **Depth indicator:** Security NFR addressed with a named SF mechanism
- **Components to search for:**
  - security NFR addressed
  - addressed via a named Salesforce mechanism
- **Source:** Well-Architected (Trusted pillar)
- **Severity if absent:** High
- **Applies:** `ALL`

#### `2B.scalability`: Scalability NFR **★**

- **Depth indicator:** Scalability NFR addressed with a named SF mechanism
- **Components to search for:**
  - scalability NFR addressed
  - addressed via a named Salesforce mechanism
- **Source:** Well-Architected (Adaptable pillar)
- **Severity if absent:** High
- **Applies:** `ALL`

#### `2B.compliance`: Compliance NFR **★**

- **Depth indicator:** Compliance NFR addressed with a named SF mechanism
- **Components to search for:**
  - compliance NFR addressed
  - addressed via a named Salesforce mechanism
- **Source:** Well-Architected (Trusted pillar)
- **Severity if absent:** High
- **Applies:** `REGULATED`

### 2C: Gap / risk identification

#### `2C.complex_flagged_risk`: Complex items flagged as risk

- **Depth indicator:** Every Complex configuration item is flagged as a risk
- **Components to search for:**
  - every Complex configuration item is flagged as a risk
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `ALL`

#### `2C.gap_id`: Requirement gaps flagged **★**

- **Depth indicator:** Unmet/ambiguous requirements explicitly flagged
- **Components to search for:**
  - unmet requirements explicitly flagged
  - ambiguous requirements explicitly flagged
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `ALL`

#### `2C.risk_id`: Delivery risks named **★**

- **Depth indicator:** Material delivery risks named with impact
- **Components to search for:**
  - material delivery risks named
  - each risk has stated impact
- **Source:** Zennify SDD standard
- **Severity if absent:** Medium
- **Applies:** `ALL`

---

## Dimension 3: Salesforce Solution Fit

### 3A: Cloud / module selection

#### `3A.cloud_products`: Cloud + products named

- **Depth indicator:** The SDD names the specific Salesforce clouds, products, and the core data model approach
- **Components to search for:**
  - specific Salesforce clouds named
  - specific products named
  - core data model approach stated
- **Source:** Well-Architected (Easy pillar)
- **Severity if absent:** High
- **Applies:** `ALL`

#### `3A.platform_native_first`: Platform-native first **★**

- **Depth indicator:** Native capability preferred over custom, justified
- **Components to search for:**
  - platform-native features chosen over AppExchange where applicable
  - AppExchange choices have justification
- **Source:** Well-Architected (Easy pillar)
- **Severity if absent:** High
- **Applies:** `ALL`

#### `3A.license_fit`: License fit for solution **★**

- **Depth indicator:** Chosen products/edition support the personas and feature set
- **Components to search for:**
  - license type identified per persona
  - license fit for the persona's capabilities verified
- **Source:** Zennify SDD standard
- **Severity if absent:** Medium
- **Applies:** `ALL`

### 3B: Trusted design

#### `3B.org`: Org-wide security **★**

- **Depth indicator:** OWD baseline + session/password/login-IP settings addressed
- **Components to search for:**
  - OWD baseline named per applicable object
  - session / password / login-IP settings addressed where in scope
- **Source:** Well-Architected (Trusted pillar)
- **Severity if absent:** High
- **Applies:** `ALL`

#### `3B.object`: Object access **★**

- **Depth indicator:** Object CRUD via permission sets, named
- **Components to search for:**
  - object-level permission strategy (CRUD) named
  - tied to permission set / profile assignment
- **Source:** Well-Architected (Trusted pillar)
- **Severity if absent:** High
- **Applies:** `ALL`

#### `3B.field`: Field access (FLS) **★**

- **Depth indicator:** FLS via permission set (not profile), named fields
- **Components to search for:**
  - field-level security strategy named
  - FLS configured via permission set (not profile-only)
- **Source:** Well-Architected (Trusted pillar)
- **Severity if absent:** High
- **Applies:** `ALL`

#### `3B.record`: Record access / sharing **†** **★**

- **Depth indicator:** OWD plus a named sharing mechanism (rule/manual/Apex)
- **Components to search for:**
  - OWD baseline named per object
  - named sharing mechanism (criteria-based rule / manual share / Apex managed / team)
  - mechanism is specific to the use case, not boilerplate
- **Source:** Well-Architected (Trusted pillar)
- **Severity if absent:** Critical
- **Applies:** `ALL`

#### `3B.action`: Action / UI-level access **★**

- **Depth indicator:** Which actions/quick-actions each persona may invoke is constrained
- **Components to search for:**
  - which actions/quick-actions each persona may invoke is constrained
  - via permission set or layout assignment
- **Source:** Well-Architected (Trusted pillar)
- **Severity if absent:** Medium
- **Applies:** `ALL`

#### `3B.apex`: Programmatic enforcement **★**

- **Depth indicator:** with/without sharing + stripInaccessible for code paths
- **Components to search for:**
  - Apex sharing strategy named where Apex DML is in scope
  - with-sharing / without-sharing decision rationale present
- **Source:** Well-Architected (Trusted pillar)
- **Severity if absent:** High
- **Applies:** `AUTOMATION`

#### `3B.integration_user`: Integration user model **★**

- **Depth indicator:** Named integration user with least-privilege permission set
- **Components to search for:**
  - named integration user identified
  - with least-privilege permission set
- **Source:** Well-Architected (Trusted pillar)
- **Severity if absent:** High
- **Applies:** `INTEGRATIONS`

#### `3B.external_user_exposure`: External-user exposure **†** **★**

- **Depth indicator:** Experience Cloud external access model and sharing named
- **Components to search for:**
  - Experience Cloud external access model named
  - external-user sharing strategy named (sharing set / share group)
  - external surface is bounded explicitly
- **Source:** Well-Architected (Trusted pillar)
- **Severity if absent:** Critical
- **Applies:** `EXTERNAL_USERS`

#### `3B.encryption_shield`: Encryption / Shield **★**

- **Depth indicator:** Shield/encryption where data sensitivity requires
- **Components to search for:**
  - shield/encryption where data sensitivity requires
- **Source:** Well-Architected (Trusted pillar)
- **Severity if absent:** High
- **Applies:** `REGULATED`

#### `3B.auditability`: Auditability **★**

- **Depth indicator:** FieldHistory / Shield Event Monitoring named for audit needs
- **Components to search for:**
  - fieldHistory / Shield Event Monitoring named for audit needs
- **Source:** Well-Architected (Trusted pillar)
- **Severity if absent:** High
- **Applies:** `REGULATED`

#### `3B.data_retention`: Data retention **★**

- **Depth indicator:** Retention / archival policy named
- **Components to search for:**
  - retention / archival policy named
- **Source:** Well-Architected (Trusted pillar)
- **Severity if absent:** Medium
- **Applies:** `REGULATED`

#### `3B.regulatory_control_mapping`: Regulatory control mapping **★**

- **Depth indicator:** Each cited regulation mapped to a concrete control
- **Components to search for:**
  - each cited regulation mapped to a concrete control
- **Source:** Well-Architected (Trusted pillar)
- **Severity if absent:** High
- **Applies:** `REGULATORY_CITATION`

### 3C: Easy design

#### `3C.sf_mechanism_named`: SF Mechanism names the feature

- **Depth indicator:** Every Configuration row names the actual feature; no 'automation'/'configuration'
- **Components to search for:**
  - every Configuration row names the actual feature
  - no 'automation'/'configuration'
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `AUTOMATION`

#### `3C.declarative_first`: Declarative-first **★**

- **Depth indicator:** Declarative preferred; Apex (Complex) justified
- **Components to search for:**
  - declarative-first approach evident (Flow before Apex)
  - Apex selections have explicit justification
- **Source:** Well-Architected (Easy pillar)
- **Severity if absent:** High
- **Applies:** `ALL`

#### `3C.execution_context`: Execution context/order **★**

- **Depth indicator:** Automation execution context / order-of-execution addressed
- **Components to search for:**
  - automation execution context named (before/after, trigger order)
  - order-of-execution implications addressed
- **Source:** Well-Architected (Easy pillar)
- **Severity if absent:** High
- **Applies:** `AUTOMATION`

#### `3C.bulk_behavior`: Bulk behaviour **★**

- **Depth indicator:** Automation designed bulk-safe (no DML/SOQL in loop)
- **Components to search for:**
  - automation designed bulk-safe
  - no DML or SOQL inside loops
- **Source:** Well-Architected (Easy pillar)
- **Severity if absent:** High
- **Applies:** `AUTOMATION`

#### `3C.recursion_control`: Recursion control **★**

- **Depth indicator:** Recursion / re-entry guard named
- **Components to search for:**
  - recursion / re-entry guard named
- **Source:** Well-Architected (Easy pillar)
- **Severity if absent:** High
- **Applies:** `TRIGGERS`

#### `3C.transaction_boundaries`: Transaction boundaries **★**

- **Depth indicator:** Sync vs async and transaction boundaries decided
- **Components to search for:**
  - sync vs async
  - transaction boundaries decided
- **Source:** Well-Architected (Easy pillar)
- **Severity if absent:** Medium
- **Applies:** `AUTOMATION`

#### `3C.error_handling`: Automation error handling **★**

- **Depth indicator:** Error/fault handling designed for automation
- **Components to search for:**
  - error/fault handling designed for automation
- **Source:** Well-Architected (Easy pillar)
- **Severity if absent:** High
- **Applies:** `AUTOMATION`

#### `3C.testability`: Testability **★**

- **Depth indicator:** Test/coverage approach stated for custom work
- **Components to search for:**
  - test/coverage approach stated for custom work
- **Source:** Well-Architected (Easy pillar)
- **Severity if absent:** Medium
- **Applies:** `CUSTOM_BUILD`

#### `3C.design_standards_naming`: Design standards / naming

- **Depth indicator:** AD numbering convention + consistent naming applied
- **Components to search for:**
  - AD numbering convention + consistent naming applied
- **Source:** Zennify SDD standard
- **Severity if absent:** Low
- **Applies:** `ALL`

#### `3C.dynamic_forms`: Dynamic Forms **★**

- **Depth indicator:** Dynamic Forms / Dynamic Actions over static layouts
- **Components to search for:**
  - dynamic Forms / Dynamic Actions over static layouts
- **Source:** Well-Architected (Easy pillar)
- **Severity if absent:** Medium
- **Applies:** `UI_IN_SCOPE`
#### `3C.async_volume_strategy`: Async / volume processing strategy **★**

- **Depth indicator:** Where data volume or long-running work warrants it, an asynchronous processing mechanism (Batch / Queueable / Scheduled Apex or async Flow path) is chosen and justified over synchronous execution
- **Components to search for:**
  - high-volume or long-running work identified where present
  - asynchronous mechanism named (Batch Apex / Queueable / Scheduled / async path)
  - the sync-vs-async choice is justified for the workload
- **Source:** Well-Architected (Adaptable pillar)
- **Severity if absent:** Medium
- **Applies:** `AUTOMATION`


### 3D: Adaptable design

#### `3D.separation_of_concerns`: Separation of concerns **★**

- **Depth indicator:** Concerns separated (handler/service/selector or equivalent)
- **Components to search for:**
  - Apex concerns separated (handler / service / selector or equivalent)
  - single-trigger-per-object pattern followed
- **Source:** Well-Architected (Adaptable pillar)
- **Severity if absent:** Medium
- **Applies:** `ALL`

#### `3D.custom_metadata_config`: Config via custom metadata

- **Depth indicator:** Variable config externalised to Custom Metadata Type (named in SF Mechanism)
- **Components to search for:**
  - variable configuration externalised to Custom Metadata Type
  - Custom Metadata Type named explicitly
- **Source:** Well-Architected (Adaptable pillar)
- **Severity if absent:** Medium
- **Applies:** `CONFIG_DRIVEN`

#### `3D.trigger_framework`: Trigger framework **★**

- **Depth indicator:** One-trigger-per-object / framework pattern
- **Components to search for:**
  - one-trigger-per-object / framework pattern
- **Source:** Well-Architected (Adaptable pillar)
- **Severity if absent:** High
- **Applies:** `TRIGGERS`

#### `3D.platform_events`: Event-driven / Platform Events **★**

- **Depth indicator:** Platform Events / CDC where async decoupling is warranted
- **Components to search for:**
  - platform Events / CDC where async decoupling is warranted
- **Source:** Well-Architected (Adaptable pillar)
- **Severity if absent:** Medium
- **Applies:** `INTEGRATIONS`

#### `3D.upgrade_safe_patterns`: Upgrade-safe patterns **★**

- **Depth indicator:** Patterns chosen to survive package/platform upgrades
- **Components to search for:**
  - patterns chosen to survive package/platform upgrades
- **Source:** Well-Architected (Adaptable pillar)
- **Severity if absent:** Medium
- **Applies:** `ALL`

#### `3D.api_versioning`: API versioning **★**

- **Depth indicator:** API versions pinned and version strategy stated
- **Components to search for:**
  - API versions pinned
  - version strategy stated
- **Source:** Well-Architected (Adaptable pillar)
- **Severity if absent:** Medium
- **Applies:** `API`

#### `3D.platform_error_handling`: Platform error strategy **★**

- **Depth indicator:** Design-level error strategy beyond per-integration
- **Components to search for:**
  - integration error handling strategy named
  - retry / dead-letter / monitoring approach specified per integration
- **Source:** Well-Architected (Adaptable pillar)
- **Severity if absent:** Medium
- **Applies:** `ALL`

### 3E: Multi-cloud architecture

#### `3E.cross_cloud_data_flow`: Cross-cloud data flow **★**

- **Depth indicator:** Data flow across clouds named with mechanism
- **Components to search for:**
  - data flow across clouds named with mechanism
- **Source:** Well-Architected (Adaptable pillar)
- **Severity if absent:** High
- **Applies:** `MULTI_CLOUD`

#### `3E.identity_federation`: Identity federation **★**

- **Depth indicator:** Identity/SSO across clouds addressed
- **Components to search for:**
  - identity/SSO across clouds addressed
- **Source:** Well-Architected (Trusted pillar)
- **Severity if absent:** High
- **Applies:** `MULTI_CLOUD`

#### `3E.license_optimisation`: Cross-cloud license optimisation **★**

- **Depth indicator:** License footprint optimised across clouds
- **Components to search for:**
  - license footprint optimised across clouds
- **Source:** Zennify SDD standard
- **Severity if absent:** Medium
- **Applies:** `MULTI_CLOUD`

---

## Dimension 4: Design Specificity

### 4A: Component presence

#### `4A.document_overview`: Solution overview

- **Depth indicator:** A high-level solution overview names the platform/cloud narrative and the integration landscape
- **Components to search for:**
  - a high-level solution overview names the platform/cloud narrative
  - the integration landscape
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `ALL`

#### `4A.capability_modules`: Capability decomposition **†**

- **Depth indicator:** Each in-scope capability is broken out as a discrete design unit with a business objective and feature-level breakdown
- **Components to search for:**
  - each in-scope capability is broken out as a discrete design unit
  - each capability has a stated business objective
  - each capability has a feature-level breakdown
- **Source:** Zennify SDD standard
- **Severity if absent:** Critical
- **Applies:** `ALL`

#### `4A.config_table`: Feature configuration breakdown

- **Depth indicator:** Each capability is decomposed into discrete features, each with implementation detail, named Salesforce mechanism, and complexity rating
- **Components to search for:**
  - each capability decomposed into discrete features
  - each feature has implementation detail
  - each feature names its Salesforce mechanism
  - each feature carries a complexity rating
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `ALL`

#### `4A.data_model`: Data model specificity **†**

- **Depth indicator:** Custom objects are named (API name, relationships, record types) and field extensions are specified with type and purpose
- **Components to search for:**
  - custom objects named at API-name level
  - object relationships specified (Master-Detail vs Lookup)
  - record types per object specified where applicable
  - field extensions specified with type and stated purpose
- **Source:** Zennify SDD standard
- **Severity if absent:** Critical
- **Applies:** `ALL`

#### `4A.record_types`: Record type catalog

- **Depth indicator:** Where record types are used, each is named with parent object, business purpose, and the user stories driving it
- **Components to search for:**
  - where record types are used, each is named with parent object, business purpose
  - the user stories driving it
- **Source:** Zennify SDD standard
- **Severity if absent:** Medium
- **Applies:** `ALL`

#### `4A.lightning_pages`: Lightning page mapping

- **Depth indicator:** Where UI is in scope, each Lightning page is named with target persona, purpose, and the user stories driving it
- **Components to search for:**
  - where UI is in scope, each Lightning page is named with target persona, purpose
  - the user stories driving it
- **Source:** Zennify SDD standard
- **Severity if absent:** Medium
- **Applies:** `UI_IN_SCOPE`

#### `4A.user_story_coverage`: Story coverage summary **†**

- **Depth indicator:** An explicit coverage summary lists every BRD story with its mapped design element(s) and status (covered, deferred, excluded)
- **Components to search for:**
  - explicit coverage summary present in the SDD
  - every BRD story listed with its mapped design element(s)
  - status per story (covered / deferred / excluded)
- **Source:** Zennify SDD standard
- **Severity if absent:** Critical
- **Applies:** `ALL`

#### `4A.security_sharing_model`: Holistic security & sharing coverage **†** **★**

- **Depth indicator:** The SDD covers the security and sharing model holistically - record-level access, org-wide settings, field-level security, permission sets, and integration security as applicable to the engagement
- **Components to search for:**
  - record-level access addressed
  - org-wide settings addressed
  - field-level security addressed
  - permission sets addressed
  - integration security addressed where applicable
- **Source:** Well-Architected (Trusted pillar)
- **Severity if absent:** Critical
- **Applies:** `ALL`

#### `4A.integration_design`: Integration design specificity

- **Depth indicator:** Per-integration design is present and substantive (mechanism, pattern, frequency, error handling)
- **Components to search for:**
  - per-integration design is present
  - substantive (mechanism, pattern, frequency, error handling)
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `INTEGRATIONS`

#### `4A.data_migration_design`: Data migration design

- **Depth indicator:** Where migration is in scope, the SDD addresses load, deduplication, cutover, and external IDs - or explicitly calls for a separate migration assessment
- **Components to search for:**
  - where migration is in scope, the SDD addresses load, deduplication, cutover
  - external IDs - or explicitly calls for a separate migration assessment
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `DATA_MIGRATION`
#### `4A.reporting_analytics`: Reporting and analytics design

- **Depth indicator:** Reporting and analytics needs are designed: report types, key reports/dashboards, and the audience and access model for analytics are named
- **Components to search for:**
  - report types or reporting objects named
  - key reports and/or dashboards named with their purpose
  - analytics audience and access/folder-sharing model addressed
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `ALL`

#### `4A.business_process_flows`: Business process flows

- **Depth indicator:** Each in-scope business process is described end-to-end: trigger, the sequence of steps, the persona/system performing each, and the outcome
- **Components to search for:**
  - in-scope business processes identified
  - each process described as an ordered sequence of steps (trigger to outcome)
  - persona or system responsible for each step named
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `ALL`

#### `4A.open_decisions_log`: Open decisions log

- **Depth indicator:** Unresolved design decisions and open questions are surfaced with the decision owner and the impact if unresolved
- **Components to search for:**
  - open decisions or open questions surfaced explicitly
  - owner named for each open item
  - impact or what-it-blocks stated for each open item
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `ALL`

#### `4A.confidence_annotations`: Confidence annotations

- **Depth indicator:** Assumption-based or provisional design elements carry a confidence/certainty marker tied to the specific section, so the reader can distinguish firm design from provisional design
- **Components to search for:**
  - confidence or certainty markers present on provisional design elements
  - markers tied to specific sections or decisions (not a blanket caveat)
  - at least the high-risk / low-confidence areas explicitly flagged
- **Source:** Zennify SDD standard
- **Severity if absent:** Medium
- **Applies:** `ALL`


### 4B: Architectural decision quality

#### `4B.ad_per_module`: Architectural decisions per capability

- **Depth indicator:** At least one explicit architectural decision (option, choice, trade-off) is recorded per major capability
- **Components to search for:**
  - at least one architectural decision per major capability
  - decision records option(s), choice, trade-off
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `ALL`

#### `4B.decision`: AD: decision stated

- **Depth indicator:** Each AD states the decision explicitly
- **Components to search for:**
  - each AD states the decision explicitly
  - the choice is named, not just the topic
- **Source:** Zennify SDD standard
- **Severity if absent:** Medium
- **Applies:** `ALL`

#### `4B.rationale`: AD: rationale

- **Depth indicator:** Each AD states rationale
- **Components to search for:**
  - each AD states the rationale for the choice
  - rationale is specific to engagement context
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `ALL`

#### `4B.options_context`: Decisions show options + context **★**

- **Depth indicator:** Each architectural decision records the options considered, the rationale for the choice made, and the engagement context that drove it
- **Components to search for:**
  - options considered named
  - rationale for choice stated
  - engagement context that drove the decision stated
- **Source:** Zennify SDD standard
- **Severity if absent:** Medium
- **Applies:** `ALL`

#### `4B.trade_offs`: AD: trade-offs **★**

- **Depth indicator:** Trade-offs of the chosen option acknowledged
- **Components to search for:**
  - trade-offs of the chosen option acknowledged
  - what is given up by this choice is named
- **Source:** Zennify SDD standard
- **Severity if absent:** Medium
- **Applies:** `ALL`

#### `4B.simpler_alternative`: Simpler/safer alternative evaluated **★**

- **Depth indicator:** For Complex items, a simpler declarative/OOTB alternative is evaluated
- **Components to search for:**
  - for Complex items, a simpler declarative/OOTB alternative is evaluated
  - rationale for not selecting the simpler path is stated
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `CUSTOM_BUILD`

---

## Dimension 5: Dependencies and Assumptions

### 5A: Dependency identification / classification

#### `5A.cross_module_dependencies`: Cross-capability dependencies

- **Depth indicator:** Dependencies between capabilities are listed with description, impact, and severity
- **Components to search for:**
  - dependencies between capabilities listed
  - each with description and impact
  - each with severity
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `ALL`

#### `5A.named_systems`: Named external systems

- **Depth indicator:** Integrations name the external system, direction, purpose
- **Components to search for:**
  - external system named
  - integration direction (inbound / outbound / bidirectional)
  - purpose of integration stated
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `INTEGRATIONS`

#### `5A.pattern_frequency`: Integration pattern + frequency

- **Depth indicator:** Integration Summary states Pattern and Frequency (SDD-only, not BRD)
- **Components to search for:**
  - integration Summary states Pattern
  - frequency (SDD-only, not BRD)
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `INTEGRATIONS`

#### `5A.api_version_auth_sla`: API version / auth / SLA **★**

- **Depth indicator:** Per integration: API version, auth model, SLA stated
- **Components to search for:**
  - API version stated per integration
  - authentication mechanism named
  - SLA or rate limit stated
- **Source:** Well-Architected (Adaptable pillar)
- **Severity if absent:** High
- **Applies:** `API`

### 5B: Assumption documentation

#### `5B.assumed_inplace`: Assumed in-place integrations

- **Depth indicator:** Existing or assumed-in-place integrations are explicitly stated as assumptions
- **Components to search for:**
  - existing integrations stated as assumptions
  - assumed-in-place systems named
- **Source:** Zennify SDD standard
- **Severity if absent:** Medium
- **Applies:** `ALL`

#### `5B.assumptions_explicit`: Assumptions explicit **★**

- **Depth indicator:** Material assumptions stated explicitly and testably
- **Components to search for:**
  - each assumption has a named owner
  - each has a validation plan
  - each has consequence if invalid
- **Source:** Zennify SDD standard
- **Severity if absent:** Medium
- **Applies:** `ALL`

### 5C: Integration failure modes

#### `5C.retry_fallback`: Retry / fallback narrative

- **Depth indicator:** Per-integration trigger & flow narrative covers happy path + retry/fallback
- **Components to search for:**
  - retry strategy named per integration
  - retry mechanism is specific (exponential backoff / circuit breaker / fixed)
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `INTEGRATIONS`

#### `5C.field_mapping`: Field mapping + transformation

- **Depth indicator:** Field Mapping table with columns Source, Source System, Target, and Transformation Notes
- **Components to search for:**
  - field mapping table present
  - columns: Source, Source System, Target, Transformation Notes
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `INTEGRATIONS`

#### `5C.integration_ad`: Architectural decisions per integration

- **Depth indicator:** At least one explicit architectural decision per integration (pattern choice, error strategy, mapping decision)
- **Components to search for:**
  - at least one architectural decision per integration
  - decision covers pattern, error strategy, or mapping
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `INTEGRATIONS`

#### `5C.idempotency`: Idempotency **★**

- **Depth indicator:** Idempotency / duplicate-handling addressed
- **Components to search for:**
  - idempotency guarantee strategy named per integration
  - approach is specific (idempotency key / dedup logic)
- **Source:** Well-Architected (Adaptable pillar)
- **Severity if absent:** High
- **Applies:** `INTEGRATIONS`

---

## Dimension 6: Scope Discipline

### 6A: In / out delineation

#### `6A.out_of_scope_callout`: Out-of-scope callout per module

- **Depth indicator:** Each module has an OUT OF SCOPE callout naming excluded higher-complexity alternatives
- **Components to search for:**
  - out-of-scope items listed explicitly
  - each with rationale or named alternative
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `ALL`

#### `6A.exclusion_specificity`: Exclusions named specifically

- **Depth indicator:** No vague terms ('advanced features'); the excluded alternative is named
- **Components to search for:**
  - no vague exclusion terms ('advanced features')
  - excluded alternative is named specifically
- **Source:** Zennify SDD standard
- **Severity if absent:** Medium
- **Applies:** `ALL`

#### `6A.scope_boundary_table`: Scope boundary with story references

- **Depth indicator:** Scope boundary items are listed with SOW cap and story references aligned to BRD deliverables
- **Components to search for:**
  - in-scope items listed explicitly
  - tied to BRD story IDs or capability names
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `ALL`

### 6B: Phasing / prioritisation

#### `6B.no_future_phase_creep`: No future-phase creep

- **Depth indicator:** No future-phase references; discovery validates, does not expand scope
- **Components to search for:**
  - no future-phase references introducing new scope
  - discovery validates rather than expands scope
- **Source:** Zennify SDD standard
- **Severity if absent:** Medium
- **Applies:** `ALL`

#### `6B.coverage_before_handoff`: Coverage complete before hand-off

- **Depth indicator:** All stories show coverage before SOW hand-off
- **Components to search for:**
  - all stories show coverage before SOW hand-off
  - coverage is auditable, not asserted
- **Source:** Zennify SDD standard
- **Severity if absent:** Medium
- **Applies:** `ALL`

### 6C: Scope-creep resistance

#### `6C.context_not_contractual`: Context not presented as deliverable

- **Depth indicator:** Assumed business process / background not presented as contractual deliverables
- **Components to search for:**
  - assumed business process / background not presented as contractual deliverables
- **Source:** Zennify SDD standard
- **Severity if absent:** Medium
- **Applies:** `ALL`

#### `6C.no_unrequested_build`: No unrequested build **★**

- **Depth indicator:** No design elements beyond BRD scope without a flag
- **Components to search for:**
  - no design elements beyond BRD scope without a flag
- **Source:** Zennify SDD standard
- **Severity if absent:** Medium
- **Applies:** `ALL`

---

## Dimension 7: Estimation Readiness

### 7A: Estimable work units

#### `7A.feature_decomposition`: Feature-level decomposition

- **Depth indicator:** Each capability is decomposed into discrete feature-level work units with implementation detail
- **Components to search for:**
  - each design element decomposed into discrete work item
  - build-vs-configure distinguished per item
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `ALL`

#### `7A.mechanism_enables_mapping`: Mechanism enables scope mapping

- **Depth indicator:** Named SF Mechanism is specific enough to drive scope-item mapping in Step 4
- **Components to search for:**
  - named Salesforce mechanism is specific
  - specificity sufficient for scope-item mapping downstream
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `ALL`

### 7B: Complexity / effort indicators

#### `7B.complexity_rating`: Complexity rating per feature

- **Depth indicator:** Each feature rated Simple / Moderate / Complex
- **Components to search for:**
  - each work item has Simple / Moderate / Complex rating
  - rating basis stated (volume / customisation / integration count)
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `ALL`

#### `7B.complex_risk_flag`: Complex flagged as risk

- **Depth indicator:** Complex items explicitly flagged as risks
- **Components to search for:**
  - complex items explicitly flagged as risks
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `ALL`

### 7C: Delivery-readiness signals

#### `7C.boundary_alignment`: Boundaries align to BRD

- **Depth indicator:** Scope Boundary numbers align with BRD Deliverables table
- **Components to search for:**
  - scope boundary numbers align with BRD Deliverables table
  - alignment is one-to-one or explicitly noted
- **Source:** Zennify SDD standard
- **Severity if absent:** Medium
- **Applies:** `ALL`

#### `7C.migration_external_id_ad`: Migration External-ID + tooling ADs

- **Depth indicator:** Data Migration has an AD for tooling and one for External ID strategy
- **Components to search for:**
  - Data Migration has an AD for tooling choice
  - Data Migration has an AD for External ID strategy
- **Source:** Zennify SDD standard
- **Severity if absent:** High
- **Applies:** `DATA_MIGRATION`

---


*End of register. Companion documents: `sa-reasoning-playbook.md` (how to apply these), `sources.md` (authority citations).*