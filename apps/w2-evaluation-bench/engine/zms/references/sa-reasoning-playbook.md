# Senior SA Reasoning Playbook

*Companion to the ZMS calibration reference. Read fresh at the start of every Section D sub-batch.*

This document captures what a senior Salesforce Solution Architect does mentally when reviewing an SDD. It encodes the reasoning patterns that let a human reviewer arrive at consistent Present / Partial / Absent verdicts without needing pre-labelled exemplars. The evaluator applies this playbook to every ZMS criterion that fires for the engagement.

The playbook has six parts: the decision protocol, the five shallowness patterns, the borderline-call rules, the eight domain-specific heuristics, the anti-bias self-discipline, and the special situations.

---

## 1. The decision protocol: turning a depth_indicator into a verdict

For every ZMS criterion that fires on the engagement, the evaluator runs three steps. The data needed is in the criterion record (`depth_indicator`, `depth_indicator_components`, `source`, `severity_if_absent`, `applicability`).

### Step 1: Decompose the depth_indicator into its components

Each criterion's `depth_indicator_components` field lists the 1–6 specific things the SDD must contain for full credit. This decomposition is pre-computed for criteria where the depth_indicator hides multiple components in prose; for criteria where the depth_indicator is atomic, the single component is the whole indicator.

The components are what to search for. They are not stylistic, they describe substantive content (named mechanism, named element, specific value, stated rationale). Do not interpret a component generously; if the component says "named sharing mechanism," boilerplate ("sharing handled appropriately") does not satisfy it.

### Step 2: Search the SDD for each component

For each component, find evidence anywhere in the SDD. Section headings are irrelevant. What matters is whether the substantive content exists in the document. A component is **present** if and only if:

- The substantive content is explicitly named (specific mechanism, specific element, specific value)
- The evidence is auditable, a verbatim ≤30-word passage can be quoted as the anchor
- The content is non-trivial (not vague placeholder, not boilerplate, not promise-to-define-later)

A component is **partial** if the topic is addressed but specificity is insufficient (right vocabulary, wrong depth). A component is **absent** if no relevant content is found anywhere in the SDD.

### Step 3: Aggregate components into the criterion verdict

| Components present | Components partial | Components absent | Verdict |
|---|---|---|---|
| All | None | None | **Present** |
| Some + others Partial | (any) | None | **Partial** |
| All but with insufficient depth | (any) | (any) | **Partial** |
| None | Any | (any) | **Partial** |
| None | None | All | **Absent** |

The verdict feeds the content-analysis coding (which becomes the within-band score for the parent sub-criterion). A criterion is **NA** when its applicability flag does not fire for the engagement never use NA to mask omission.

### A worked example: `3B.record` (Critical floor)

`depth_indicator_components`:
1. OWD baseline named per object
2. Named sharing mechanism (criteria-based rule / manual share / Apex managed / team)
3. Mechanism is specific to the use case, not boilerplate

Candidate SDD text §3.4: *"OWD set to Private. Sharing rule `Account_Region_R1` shares Account to Regional Sales Team when Region__c = Active."*

- Component 1 (OWD baseline): Present, "OWD set to Private" is specific
- Component 2 (named mechanism): Present, `Account_Region_R1` is a specific named sharing rule
- Component 3 (use-case-specific): Present, the rule is tied to a specific field condition

Verdict: **Present**. Evidence anchor: §3.4 verbatim.

Same criterion, different candidate SDD: *"OWD will be set appropriately. Sharing will follow Salesforce best practices."*

- Component 1: Partial, "appropriately" is not specific
- Component 2: Absent, no mechanism named
- Component 3: Absent, boilerplate

Verdict: **Absent**. Critical floor activates Dim 3 capped accordingly per the rubric.

### A second worked example: `1A.field` (illustrating Present + Partial)

`depth_indicator_components`:
1. Field extension named
2. Field type specified
3. Stated purpose for each field

Candidate SDD §4.2: *"`Account.Risk_Tier__c` (Picklist: Low/Medium/High), used by sharing rule `Account_Region_R1` to scope record visibility."*

- Component 1 (field extension named): Present, `Risk_Tier__c` is named with API convention
- Component 2 (field type specified): Present, "Picklist: Low/Medium/High" specifies type and values
- Component 3 (stated purpose): Present, purpose is named ("used by sharing rule…")

Verdict: **Present**. Evidence anchor: §4.2 verbatim.

Same criterion, different candidate SDD §4.2: *"Custom fields will be added to Account to support the new sharing requirements."*

- Component 1: Absent, no fields named
- Component 2: Absent, no types specified  
- Component 3: Partial, purpose is gestured at ("sharing requirements") but generically

Verdict: **Partial** (one component partial, two absent; not enough for Absent because there is *some* gesture at intent, but well short of Present).

---

## 2. Recognising shallowness: the five patterns

Senior SAs recognise these instantly because they cause real delivery problems. When the SDD exhibits one of these patterns on a topic, do not credit the topic as Present.

### Pattern 1: The platform asserter

> *"Security will be handled by the Salesforce platform."*  
> *"Standard sharing model will apply."*  
> *"We will follow Salesforce best practices."*

These assert that something will happen without naming what. **Verdict on the affected component: Absent** unless specific mechanisms are named elsewhere in the SDD. The platform does not configure itself.

### Pattern 2: The generic placeholder

> *"Configuration will be defined as needed."*  
> *"Custom logic will be implemented to meet requirements."*  
> *"The data model will support the use cases."*

Promises specificity without delivering it. **Verdict: Absent.** A design with placeholders is not a design.

### Pattern 3: The token vocabulary

> *"We will use permission sets to manage access."*  
> *"OWD will be set to Private."* (alone, no sharing mechanism)  
> *"Flow will handle the automation."* (which Flow? triggered by what?)

Uses the right vocabulary without specifying choices. **Verdict: Partial at best, Absent if the vocabulary is the entire content.** Vocabulary correctness is not design correctness.

### Pattern 4: The unsupported assertion

> *"Apex is the right choice here."* (with no trade-off analysis)  
> *"This integration will use REST."* (with no rationale for sync vs async)

Makes architectural choices without showing reasoning. **Verdict: Partial.** The choice may be correct, but criteria that require options-plus-rationale (most of Dim 4B) are not satisfied without the reasoning shown.

### Pattern 5: The displaced answer

> Security mentioned only in the Assumptions section.  
> Integration error handling buried in an open-questions list.  
> Data model fragments scattered across executive summary and appendix.

Substance may exist but isn't auditable where the criterion expects it. **Verdict: Partial** if the substance is genuinely there (criterion-by-criterion judgement); **Absent** if the displacement is also accompanied by shallow content.

---

## 3. Borderline calls: explicit resolution rules

When uncertain between two verdicts, apply these tests in order.

### Present vs Partial

> *"Could a developer start work on this immediately, or would they need to ask clarifying questions?"*

- Developer can start work → **Present**
- Developer would need clarifying questions → **Partial**

### Partial vs Absent

> *"Does the SDD address this topic with any specificity, or only as boilerplate?"*

- Any specificity at all → **Partial**
- Boilerplate-only or topic missing entirely → **Absent**

### Applicable vs NA

> *"Does the engagement (per applicability flags from intake) require this, or is the criterion irrelevant?"*

- Engagement requires it → score Present / Partial / Absent (omission is not NA)
- Applicability flag doesn't fire → **NA** (criterion excluded from scoring)

The applicability check happens before scoring, not after. A criterion that fires per the flags but isn't addressed in the SDD scores Absent, not NA.

---

## 4. Domain reasoning heuristics

Eight high-stakes areas where the senior SA brings additional knowledge beyond the depth_indicator. Use these as anchors when the depth_indicator alone leaves room for interpretation.

### Security & sharing (3B.*, 4A.security_sharing_model, 1B.persona_record_visibility)

Senior SAs look for: OWD baseline per object, named sharing mechanism (criteria-based rule / manual share / Apex managed / team-based), persona-level visibility logic, FLS strategy via permission set (not profile), integration user model with least-privilege, external user surface bounded (when Experience Cloud is in scope).

Most common shallowness: OWD named without sharing mechanism, or platform-asserter boilerplate. Both score Absent on the affected criteria because the actual access logic is missing.

Critical distinction:
- `3B.record` is the *technical mechanism* for record-level access (OWD + named rule).
- `4A.security_sharing_model` is the *holistic coverage* of all five layers (record-level + org-wide + FLS + permission sets + integration security).

These are scored independently. Do not double-count one gap as both criteria.

### Integrations (3D.*, 5A.*, 5C.*)

Senior SAs look for: per-integration mechanism (REST callout / Platform Event / MuleSoft / External Services / named middleware), pattern (sync vs async, push vs pull), frequency, idempotency strategy, retry policy, error handling, monitoring, dead-letter approach.

Most common shallowness: pattern named but error handling absent. Score **Partial** on `5C.*`, the happy path is designed, the failure path is not.

### Data model (4A.data_model, 1A.object, 1A.field)

Senior SAs look for: custom object API names, relationships (Master-Detail vs Lookup with rationale), record types per object, field-level extensions with type and stated purpose, ownership pattern, sharing implications.

Most common shallowness: objects listed without relationships. Score **Partial** on `4A.data_model`.

### Automation (3B.apex, 3C.*, 3D.platform_error_handling)

Senior SAs look for: specific mechanism per business rule (Flow / Approval Process / Apex Trigger / Validation Rule), choice rationale where Apex is selected over declarative, bulkification consideration, governor-limit awareness, error handling strategy.

Most common shallowness: *"automation will use Flow or Apex as appropriate"*, token vocabulary without per-rule decision. Score **Partial** on `1A.sf_mechanism_named` and the affected `3C.*` criteria.

### Requirements coverage (2A.*, 4A.user_story_coverage)

Senior SAs look for: every story (or every acceptance criterion) traced to a specific design element, or explicitly deferred / excluded with stated reason.

Critical distinction:
- `2A.story_coverage_complete` measures whether every story is substantively addressed *somewhere* in the SDD.
- `4A.user_story_coverage` measures whether an *explicit coverage summary* surfaces the mapping at a glance.

These are independent. An SDD can cover every story in the design body without a coverage summary (2A Present, 4A Absent), or have a coverage summary that's wrong (4A Partial, 2A potentially Present if the design actually covers the stories).

### Scope discipline (6A.*, 6B.*, 6C.*)

Senior SAs look for: in-scope list with story bindings, out-of-scope list with named alternatives and exclusion rationale, phasing if relevant, scope-creep posture (what happens if requirements expand mid-build).

Most common shallowness: in-scope clear, out-of-scope absent. Score **Partial** on `6A.*`, half the scope discipline is missing. An SDD without explicit out-of-scope is a scope-creep liability regardless of how clear the in-scope is.

### Estimation readiness (7A.*, 7B.*, 7C.*)

Senior SAs look for: discrete work units per capability (features), complexity rating per unit with basis, delivery sequence with dependencies, delivery-readiness signals (deployment mechanism, environment plan, testing approach, data migration tooling, DoD per phase).

Most common shallowness: features listed without complexity ratings. Score **Partial** on `7B.complexity_rating`, work units are present but not sized.

### Architectural decisions (4B.*)

Senior SAs look for: the decision stated explicitly, options considered, rationale for the choice, engagement context that drove it, trade-offs accepted.

Most common shallowness: decision recorded as fait accompli without options or rationale. Score **Partial** on `4B.options_context` and `4B.trade_offs`. A decision without alternatives shown is documentation, not architecture.

---

## 5. Self-discipline: the SA's own anti-bias moves

Six rules the senior SA applies to themselves while scoring. The evaluator applies them too, these prevent the most common scoring biases.

### 1. Score Output A and Output B independently before comparing

Don't let strengths of one lane influence judgement of the other. Reset between lanes. Each lane is judged against the ZMS calibration bar in isolation; the comparison only happens at lift calculation.

### 2. Reset between criteria

A weak Dim 1 verdict shouldn't pre-bias Dim 3 scoring. Each criterion gets fresh attention. Halo effects are the most common source of within-lane scoring drift.

### 3. Cite the depth_indicator verbatim in both verdicts

When recording the verdict for the same criterion on both lanes, quote the depth_indicator (or its components) verbatim in the reasoning. This proves the same standard was applied to both lanes and forces re-anchoring before each verdict.

### 4. Sample-check for drift

After scoring ~20 criteria, pick 3 at random and re-score from scratch. If verdicts shift materially, the calibration is drifting; recalibrate against the depth_indicators before continuing.

### 5. Don't reward verbosity

Long ≠ substantive. A 60-page SDD with shallow content scores lower than a 30-page SDD with substantive content. Test substance directly: does the SDD name the specific thing the depth_indicator requires? If yes, Present regardless of length. If no, not-Present regardless of length.

### 6. Don't reward (or penalise) writing polish

Polish is independent of architecture quality. A poorly-written SDD with the right substance scores Present; a beautifully-written SDD with the wrong substance scores Absent. The criterion measures content, not craft. Likewise, **section headings, layout, and table formatting are irrelevant**, substance in any layout satisfies the depth_indicator; layout without substance does not.

---

## 6. Special situations

Edge cases that mess up routine scoring. These keep the methodology honest in the corners.

### Both outputs miss the same thing

When both candidates score Absent on the same criterion, the gap is usually **methodology-wide**, not lane-specific. The BRD didn't elicit it, the in-house template didn't prompt for it, or both models lacked the domain knowledge. Flag it in the diagnostic report's framework-gap surface, distinct from ZennAgent-only gaps that the methodology team can act on.

### Length differences are not a signal

A 30-page SDD and a 60-page SDD can both score Present on every criterion. The senior SA looks for coverage *density* (every criterion has substantive content somewhere) not coverage *volume*. Score sub-criteria one at a time; don't let one lane's brevity or verbosity bias the verdicts.

### Bonus depth beyond BRD requirements

Some SDDs include design content the BRD doesn't require (observability strategy, monitoring architecture, change management approach). Do not credit this on the 99 criteria, Present is the ceiling per criterion, and the criteria measure what's required, not what's extra. Surface "bonus depth" as an informational note in the diagnostic report only; it does not raise scores.

### Conflicting evidence within one SDD

If the SDD names a specific mechanism in §3.4 and contradicts it in §5.1, the **more concrete statement wins** the verdict, but the inconsistency is logged as a finding. Internal contradictions are a quality signal in their own right.

### Token-correct boilerplate

Don't be fooled by vocabulary-correct boilerplate. The depth_indicator requires substance, not vocabulary. *"OWD is set to Private"* (alone, no sharing mechanism) uses the right vocabulary but doesn't deliver the depth indicator. Score the affected component **Partial** if other components compensate, **Absent** otherwise.

### Salesforce documentation as technical truth

On Dim 3/4/5/7 the operator BRD remains the requirements truth source, but Salesforce platform standards (Help, Architect, Well-Architected) are the technical truth source. If the SDD's choice contradicts current Salesforce guidance (e.g., recommends a retired feature, names a deprecated pattern), the criterion's verdict reflects the contradiction, this also feeds the release-awareness deduction schedule on Dim 3.

---

## Self-validation checklist before writing the scoring bundle

Before emitting the scoring bundle for a sub-batch, confirm:

- [ ] Every criterion that fired per applicability flags has a verdict (Present / Partial / Absent / NA)
- [ ] Every Present verdict has a verbatim evidence anchor ≤30 words
- [ ] Every Partial verdict explains *what's missing* in component-specific terms
- [ ] Every Absent verdict explains *what was searched for* (the depth_indicator components)
- [ ] Five-pass discipline applied at T=0.3 (variance flagged where stddev > 1.0)
- [ ] Anti-bias rules applied (lanes independent, criteria reset, depth_indicator cited)
- [ ] No `ZennAgent | ZA | off-the-shelf | OTS` tokens in any reasoning field (blinding holds)

If any item is unchecked, the bundle is incomplete. Do not write it; return to the scoring step.

---

*End of SA Reasoning Playbook v4.6. Read fresh at every Section D sub-batch invocation.*
