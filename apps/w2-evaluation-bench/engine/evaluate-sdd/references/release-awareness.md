# Release-Currency Crosswalk Methodology

*Reference for Section C.5 of evaluate-sdd v4.6. Companion to `release_crosswalk.py` (the engine; `release_awareness_check.py` remains as a register-only back-compat shim).*

> **v3.8.0 — what changed.** Section C.5 is now a **live, search-driven crosswalk**, not a static-register lookup. Live testing established that `help.salesforce.com` is a JavaScript single-page app: a direct fetch returns only a "Loading…" shell, but Salesforce's authoritative content reaches the **web-search index** with citable snippets. So the live path is **search-driven** and runs as a **two-call contract**:
>
> 1. `release_crosswalk.py extract` (no network) scans the SDD and emits each named mechanism plus a targeted search query.
> 2. The **orchestrator** runs `web_search` for each query (web tooling is available at deploy time) and writes the snippets+URLs+dates to `release-evidence-<lane>.json`. **Preferred when connected:** use the **Salesforce Docs MCP** (`salesforce_docs_search` / `salesforce_docs_fetch`) instead of generic `web_search` — it returns authoritative, cited release-note excerpts from official Salesforce docs, which are Salesforce-controlled URLs and therefore pass the R23 guard and resolve as `live_confirmed`. See `references/salesforce-docs-mcp.md`. Generic `web_search` remains the fallback when the MCP is not connected; the evidence file schema is identical either way.
> 3. `release_crosswalk.py resolve` (no network) applies the source-authority policy to the evidence + the minimal dated register and writes the findings.
>
> The **live path is primary**; `data/release-register.json` is a deliberately minimal, dated backstop. **Scoring is a confidence-based binary model:** a mechanism is either confirmed current (`in_force`, deduction 0) or it costs points. The descriptive statuses `retired` / `end_of_support` / `superseded` are retained for report detail but all share ONE unified deduction (−3) — there is no longer a −5/−3 retirement-category gradation, because category is the most drift-prone fact and is not what the score depends on. `in_force_unverified` (named but currency not confirmed) deducts −1, BUT only when the live path actually ran this lane; if the run had no web access every mechanism is unverified for a tooling reason and deducts 0 (an offline run is never penalised for a limitation it cannot control). The deduction values are single-sourced in `contracts.py` (`RR_NOT_IN_FORCE_DEDUCTION`, `RR_UNVERIFIED_DEDUCTION`, `RELEASE_SEVERITY_DEDUCTION`); cap −9/lane. Every finding is tagged with a confidence: `live_confirmed` / `register_based` / `unverified`.
>
> **Source-authority policy (the precision guard):** a non-current status may be asserted ONLY when a Salesforce-controlled URL (R23) is in the evidence. Third-party sources are stored as `corroboration[]` and can never raise a status on their own — this is what prevents the Workflow-Rules error (third-party "retired" vs Salesforce "end of support"). If live Salesforce evidence contradicts the register, live wins and the finding is flagged `register_stale`.
>
> **Recommendation sourcing (no invention):** Tier 1 = successor named in the confirming Salesforce snippet; Tier 2 = the register's `supersession` field; Tier 3 = `contracts.SUCCESSOR_UNSOURCED` ("SA to confirm current successor"). Version successors resolve live (current GA), never hardcoded. The crosswalk recommends the platform-feature/version successor; it does not redesign the capability — that is the SA's job.
>
> The sections below remain valid for the classification *reasoning*; where they reference the older four-bucket scheme, the five-status taxonomy above governs.

> **Model-driven coverage + positive grounding.** Three additions let the SDD under review (not a static list) drive what is verified, and let the audit affirmatively confirm current features:
>
> 1. **Model-driven extraction (`--features`).** `extract` always runs a deterministic regex *floor* (the known-legacy patterns) so nothing known is ever missed, AND accepts an optional `--features <file.json>` — the Salesforce features the model identified while reading the SDD, including current features the SDD *recommends* (Data Cloud, Agentforce, Dynamic Forms, etc.). Schema: `{"features": [{"name": "...", "section": "...", "quote": "..."}]}` or a bare list of names. Model features are added as a superset, deduped against the floor by normalised key (floor wins, preserving exact char-offset provenance), tagged `source: model_identified`, and each gets a currency-seeking query. This is what keeps recommendations and Dim-3 credibility grounded in the current release rather than a hardcoded catalogue. The verdict boundary is unchanged: the model sets *what to look up*; only a Salesforce-controlled source (R23) sets the *status*.
> 2. **Positive `in_force` signal.** When a Salesforce-controlled source affirmatively states a feature is current / GA / supported / recommended, the finding resolves to `in_force` with `live_confirmed` confidence — the positive grounding signal Section D reads for Dim-3 credibility. The signal is evaluated LAST, so any deprecation phrasing in the same snippet still wins. A feature with no live confirmation and no register entry stays `in_force_unverified` (surfaced, no deduction) — never a fabricated status.
> 3. **Register review-date staleness.** A register-based finding whose register entry is past its `review_by` date raises a `REGISTER-STALE` degradation banner naming the mechanism. This is surfaced only — it never changes the status or deduction (we still trust the dated fact, but flag it for re-confirmation against the Salesforce source). It is distinct from `register_stale`, which means live evidence contradicted the register *this run*.

---

*Original methodology (reasoning reference) for Section C.5.*

This document specifies how Section C.5 conducts release-currency research against Salesforce-controlled sources, how findings are classified into the five-status taxonomy (section 4), and how findings flow downstream to Dim 3 deductions (RR-* schedule) and the diagnostic report's Release Currency Audit (Appendix B).

Section C.5 runs **twice** per workflow once per SDD (Output A then Output B). Outputs are lane-isolated (`release-awareness-A.json` and `release-awareness-B.json`). The Section D evaluator consumes the per-lane findings to apply RR deductions on Dim 3; the diagnostic report assembler consumes both for the Appendix B audit.

This is a **source-anchored** process. Every finding must cite a URL on a Salesforce-controlled domain (R23). No third-party blogs, community posts, or forums as primary source. Conservative defaults: if mechanism status cannot be confirmed against a Salesforce source, classify as `in_force_unverified` and surface for SA review rather than inventing a retirement.

---

## 1. Mechanism extraction from the SDD

The first step extracts every named Salesforce mechanism the SDD claims to use. The extraction is NLP-based with a Salesforce-vocabulary keyword backbone.

### Targets extracted

- **Feature names**, *Process Builder, Workflow Rule, Flow Builder, Visualforce, Lightning Web Components, Aura, Apex Triggers, Approval Process, Validation Rule, Email-to-Case, Web-to-Case, Outbound Message, External Services, Platform Events, Change Data Capture, Streaming API, Salesforce Connect, Salesforce-to-Salesforce, etc.*
- **Cloud / product names**, *Sales Cloud, Service Cloud, Marketing Cloud (and its sub-products: Email Studio, Mobile Studio, Journey Builder, Pardot, Account Engagement, Marketing Cloud Engagement, Marketing Cloud Personalization), Experience Cloud (Communities), Data Cloud (Customer Data Platform / Genie), Financial Services Cloud, Health Cloud, Industries Cloud, Net Zero Cloud, etc.*
- **Configuration patterns**, *named permission sets, named sharing rules, named approval process names, named flow types (Screen Flow / Record-Triggered Flow / Scheduled Flow / Platform Event-Triggered Flow), named middleware (MuleSoft, Salesforce Connect, External Services).*
- **API mechanisms**, *REST API, SOAP API, Bulk API (1.0 / 2.0), Streaming API, Pub/Sub API, GraphQL, OAuth flows (Username-Password, Web Server, JWT Bearer, Refresh Token, Device, etc.).*
- **Integration patterns**, *Outbound Message, Platform Event, CDC (Change Data Capture), Apex Callout, Composite API, Salesforce Connect (OData), MuleSoft direct, External Services with OpenAPI spec.*
- **Deployment / DevOps**, *Change Sets, DevOps Center, SFDX, Salesforce CLI, Metadata API, Tooling API, scratch orgs, sandbox types (Developer / Developer Pro / Partial Copy / Full).*
- **Apex patterns**, *@future, @AuraEnabled, Batch Apex, Queueable, Schedulable, Platform Events (subscribe / publish), Transaction Finalizers, Composite Apex.*

### Extraction discipline

- **Quoted mechanism names** are preferred the SDD's actual text is the source, not paraphrase.
- **Inflection tolerated**, "Process Builder", "Process Builders", "the Process Builder approach" all resolve to the same mechanism.
- **Composite mentions split**, "Flow Builder and Apex" produces two mechanisms.
- **Generic vocabulary excluded**, "automation", "configuration", "custom logic" without a specific mechanism name do not extract (those are handled by ZMS criterion `1A.sf_mechanism_named` as Partial/Absent verdicts).
- **Conservative scoping**, when a mechanism is named only as a counter-example ("we will NOT use Process Builder"), it does not extract.

---

## 2. Salesforce-controlled source domains (R23)

Every finding's `source_url` must be on one of these Salesforce-controlled domains:

| Domain | Authority | Typical use |
|---|---|---|
| `help.salesforce.com` | Salesforce Help / Knowledge | Feature retirement notices, EOL announcements, release notes |
| `developer.salesforce.com` | Developer documentation | API versioning, Apex feature status, REST/SOAP availability |
| `architect.salesforce.com` | Well-Architected Framework | Trusted / Easy / Adaptable guidance, deprecated patterns |
| `trailhead.salesforce.com` | Trailhead training material | Current-vs-deprecated patterns in learning content |
| `admin.salesforce.com` | Admin advocacy site | Admin-facing feature status |
| `trust.salesforce.com` | Trust site | Infrastructure / security status |
| `salesforce.com` | Marketing + product pages | Product line announcements, Cloud feature gates |

**Non-Salesforce sources are rejected at validation (R23).** This includes:

- Third-party blogs, even authoritative ones (Salesforceben, Apex Hours, Sfdcdrive, MikeWheeler, etc.)
- Community sites (Salesforce Stack Exchange, Trailblazer Community, Reddit r/salesforce)
- LinkedIn posts (even from Salesforce employees acting personally)
- AppExchange listings (when used as authority, they're commercial pages, not standards)
- Archived web copies of Salesforce content (if the live page no longer exists, the mechanism's status is `in_force_unverified`, not "retired")

---

## 3. Three-tier search procedure

For each extracted mechanism, the script attempts to resolve its current status via three search tiers in order:

### Tier 1: Targeted retirement search

```
site:help.salesforce.com "{mechanism}" (retired OR EOL OR "end of life" OR sunset)
```

Yields direct hits when Salesforce has published a retirement notice. Example: "Process Builder" returns the EOL notice.

### Tier 2: Replacement-pattern search

```
site:help.salesforce.com "{mechanism}" (replacement OR migration OR "use instead")
```

Yields current Salesforce-recommended alternative. Example: "Workflow Rule" returns migration-to-Flow guidance.

### Tier 3: Current-status verification

```
site:developer.salesforce.com OR site:architect.salesforce.com "{mechanism}" 2026
```

Yields current documentation. The absence of recent documentation against a presumed-current mechanism is itself a signal worth surfacing.

If Tier 1 yields a hit → classify per the hit's content. If Tier 2 → classify as `superseded` with the replacement named. If only Tier 3 → classify as `in_force` or `in_force_unverified` depending on the recency of the documentation.

---

## 4. Classification (five-status taxonomy)

> **Deduction-model (unified) — read this before the table.** The five *status names* below are still emitted (they are useful report detail), and the classification *reasoning* in this section is still how you decide which status applies. BUT the *deduction values* shown in the table's "Severity / deduction" column are SUPERSEDED. Under the confidence-based binary model: every confirmed-not-in-force status (`retired` / `end_of_support` / `superseded`) deducts the SAME unified **−3** (the −5 vs −3 gradation is gone); `in_force` = 0; `in_force_unverified` = **−1 only when the live path ran**, else 0. The "Critical / −5" and "Major / −3" labels below describe the legacy gradation and are retained only to explain the classification reasoning — the authoritative deductions are in `contracts.py`. The descriptive distinction (e.g. "retired = won't deploy / blocking" vs "end_of_support = still runs") remains valid prose for the report; it just no longer changes the score.

> **The current taxonomy supersedes the four-bucket scheme described below.** The current taxonomy, single-sourced in `contracts.py` (`RELEASE_STATUS`, `RELEASE_SEVERITY_DEDUCTION`) and emitted by `release_crosswalk.py`, is five states. The legacy bucket names map as follows; read the legacy descriptions below for the classification *reasoning*, but emit the new status names.

| Legacy bucket | Current status | Severity / deduction (legacy) | When |
|---|---|---|---|
| `retired_postEOL` | `retired` | Critical / −5 | calls fail or won't deploy (past EOL, retired & unavailable) |
| `retired_announced` (post-EOL) | `retired` | Critical / −5 | retirement effective; the design will break |
| `retired_announced` (still runs) | `end_of_support` | Major / −3 | support/bug-fixes ended but the feature still runs (e.g. Workflow Rules, Process Builder) |
| `active_being_superseded` | `superseded` | Major / −3 | works, but a newer Salesforce-recommended standard exists and the SDD used the old one |
| `in_force` | `in_force` | none / 0 | current and appropriate |
| `in_force_unverified` | `in_force_unverified` | none / 0 (SA-review) | not confirmed against a Salesforce-controlled source |

The crucial classification correction: **End of Support is not retirement.** Workflow Rules and Process Builder reached End of Support on 2025-12-31 — they still run, so they classify as `end_of_support` (still-runs technical debt), not `retired` (won't-deploy/blocking). Under the unified model both carry the same −3 deduction, but the descriptive distinction still matters for the report prose. Third-party sources that call them "retired" cannot raise the status; only a Salesforce-controlled source can, per the source-authority policy.

---

## 4 (legacy). The four-bucket classification — reasoning reference

Each finding is classified into exactly one bucket. These bucket names map to the current statuses per the table above; the severity → deduction mapping is single-sourced in `contracts.py`.

### Bucket 1: `retired_announced` (legacy) → `retired` (post-EOL) or `end_of_support` (still runs)

Salesforce has published a retirement notice; the sunset window is active or complete. SDDs naming this mechanism are designing technical debt, or, post-EOL, designing on broken ground.

Examples:

- **Workflow Rules** → `end_of_support` (still runs after 2025-12-31; replacement: Flow)
- **Process Builder** → `end_of_support` (replacement: Record-Triggered Flow)
- **Salesforce Classic UI dependencies** → `superseded` (replacement: Lightning Experience)

Trigger (unified model): any of these confirmed-not-in-force statuses (`end_of_support`, `superseded`, or `retired`) carries the same **−3** deduction. The descriptive distinction is kept for the report prose (e.g. `retired` = won't deploy / blocking; `end_of_support` = still runs but unsupported), but it no longer changes the score.

### Bucket 2: `active_being_superseded` (legacy) → `superseded`

The mechanism works and is supported, but Salesforce recommends a successor for new designs.

Examples:

- **Aura components in greenfield** (replacement: LWC)
- **Bulk API 1.0** (replacement: Bulk API 2.0)
- **Legacy Connected App auth flows** (replacement: External Client Apps / current OAuth flows)

Triggers: **−3 (Major tier)** on Dim 3 (the legacy scheme used Minor −1; the current taxonomy treats a superseded-version dependency as Major because the SDD adopted an outdated standard).

### Bucket 3: `in_force` (severity: none)

The mechanism is current, supported, and appropriate for the SDD's context. No deduction. Surfaced in the report only as part of the audit trail (every mechanism named in the SDD appears in the Release Currency Audit, report Appendix B).

### Bucket 4: `in_force_unverified` (severity: none; SA-review flag)

The mechanism's status could not be confirmed against a Salesforce-controlled source within the research time budget. This is the **conservative default** — never a fabricated status — and the finding is flagged for SA review. Deduction under the current binary model: **−1 when the live path ran this lane** (currency was checkable but not confirmed), **0 when the run had no web access** (a tooling limit is never penalised). Where live confirmation was broadly weak this run, the WEAK-LIVE banner says so alongside the findings.

Triggers: an audit row, plus the −1 deduction when the live path ran (per `contracts.RR_UNVERIFIED_DEDUCTION`; 0 offline). The SA reviewing the diagnostic report can verify the status manually and update the bundle.

**Why this bucket matters:** the most common failure mode is the script confidently classifying a mechanism as "retired" based on a stale third-party source. Defaulting to `in_force_unverified` prevents this; uncertainty is surfaced, not papered over.

---

## 5. Finding schema

Each finding emits a JSON record matching the `Finding` dataclass in `release_awareness_check.py`:

```json
{
  "finding_id": "RR-A-001",
  "mechanism_name": "Process Builder",
  "mechanism_key": "process_builder",
  "status": "retired",
  "rr_severity": "Major",
  "rr_deduction": -3,
  "salesforce_source": "https://help.salesforce.com/s/articleView?id=sf.migrate_to_flow.htm",
  "source_retrieved_at": "2026-06-10T09:00:00+00:00",
  "supersession_recommendation": "Record-Triggered Flow",
  "evidence_note": "Salesforce has announced Process Builder retirement in favour of Flow.",
  "sdd_mentions": [{"section": "§4.2", "quote": "Process Builder will manage Account record updates"}]
}
```

Field constraints:

- `finding_id`, `RR-{A|B}-NNN` sequential per lane — this exact value is what an `RR-*` deduction's `release_finding_ref` must cite (R22)
- `mechanism_name`, the display name; `mechanism_key`, the pattern-register key that matched
- `status`, one of `retired`, `end_of_support`, `superseded`, `in_force`, `in_force_unverified`. This is the single release-currency field. (A legacy `bucket` field with four-bucket names was removed; the section-4 mapping table is kept only as reasoning reference.)
- `rr_severity`, `Major` / null (null for `in_force` and `in_force_unverified`; all confirmed-not-in-force statuses share the "Major" tier under the unified model)
- `rr_deduction`, confidence-based binary: `-3` for any confirmed-not-in-force status, `-1` for `in_force_unverified` when the live path ran (else 0), `0` for `in_force`
- `salesforce_source`, **MUST** match the R23 Salesforce-domain whitelist (non-whitelisted URLs are rejected and defaulted, with the rejection noted in `evidence_note`)
- `source_retrieved_at`, ISO timestamp of when this skill ran (provenance for the as-of claim)
- `sdd_mentions`, up to 5 `{section, quote}` records anchoring where the SDD names the mechanism

---

## 6. Cap on RR deductions

Per the Dim 3 deduction discipline (rubric §7.2): **RR deductions cap at −9 per lane.** If the SDD names four retirement-announced mechanisms, each at −3, the cumulative deduction is capped at −9, not −12. This prevents release-currency findings from completely dominating Dim 3.

The script computes the uncapped sum and the capped value; both are emitted in the digest (`rr_deductions_capped_total`) for transparency, and the cap is re-enforced at score-sheet population time.

---

## 7. R22: RR deductions cite the finding_id

Every `RR-*` deduction emitted into the scoring bundle's `deductions` array must carry a `release_finding_ref` field whose value is a `finding_id` present in the bundle's `release_awareness_findings` (copied from `release-awareness-{a|b}.json`). This is the cross-reference that makes Dim 3 scoring auditable: the SA reviewing the report can follow `RR-A-001` back to the Appendix B row that drove it, and from there to the Salesforce-controlled source URL.

R22 is enforced at score-sheet validation time. A bundle with `RR-*` deductions but no matching `finding_id` fails validation.

---

## 8. R24: Release-driven actions cite the finding_id

In the diagnostic report's §7 Recommended Actions, any action with `category: "release_currency"` must carry a `release_finding_ref` field. This is the parallel cross-reference: the action ("Replace Process Builder with Flow") must trace to the source finding ("Process Builder is deprecated; replacement is Flow Builder").

R24 is enforced at report validation time. Together with R22, this creates an end-to-end audit trail: source URL → finding → deduction → recommended action.

---

## 9. Conservative defaults: when in doubt, surface, don't invent

Three conservative-default behaviours protect the methodology against false-positive retirements:

1. **Unverified default**, if research doesn't find a Salesforce-controlled source within budget, classify `in_force_unverified` rather than guessing.
2. **Recency floor**, Salesforce documentation older than 18 months without recent confirmation is downgraded to `in_force_unverified` (the page may be stale).
3. **Contradiction handling**, if Tier 1 and Tier 3 contradict (e.g., a retirement notice exists but recent Trailhead content still teaches the mechanism), classify as `in_force_unverified` and surface both sources for SA review.

---

## 10. Per-lane isolation

Section C.5 runs once per SDD. The outputs are written to separate files:

- `release-awareness-a.json`, Output A's findings (anonymised)
- `release-awareness-b.json`, Output B's findings (anonymised)

The Section D evaluator consumes the lane-matched file for the SDD it is scoring. Blinding is preserved: the file names use the Output A/B labels assigned at intake, not ZennAgent/OTS.

Lane reveal happens at `lane_reveal_apply.py` time, after all scoring is complete. At that point the lane mapping (Output A = ZennAgent or = OTS) is applied to both lanes' findings, producing the per-lane diagnostic report sections.

---

*Release-awareness methodology v4.6. Updated when Salesforce introduces new mechanisms, deprecates current ones, or changes the structure of its help/architect documentation.*
