"""Work-packet prompt builders.

A packet is one act of model judgment, fully self-contained: instructions +
inline context + a strict output contract (JSON only). The runner executes it
verbatim under the operator's subscription and posts the JSON back. Blinding:
packet payloads are built ONLY from lane-labelled artifacts; the escrow is
never read here.
"""
from __future__ import annotations
import json
from pathlib import Path

def _json_fit(obj, max_chars: int) -> str:
    """Serialize obj, dropping whole entries (never mid-string) until it fits."""
    s = json.dumps(obj, indent=1)
    while len(s) > max_chars and isinstance(obj, dict) and len(obj) > 1:
        obj = dict(list(obj.items())[: max(1, int(len(obj) * 0.8))])
        s = json.dumps(obj, indent=1)
    return s


JSON_ONLY = ("\n\nOUTPUT CONTRACT: respond with ONE JSON object only - no prose, no "
             "markdown fences, no commentary before or after. If a field is "
             "unknowable from the material, use null; NEVER invent content.")


def _read(p: Path, limit: int | None = None) -> str:
    t = Path(p).read_text(errors="replace")
    return t if limit is None else t[:limit]


def components_prompt(sdd_path: Path, label: str) -> str:
    return f"""You are the Section C reader of the Zennify W2 evaluation pipeline.
Read the Solution Design Document below ({label}) and locate the framework's
components wherever they live (numbered sections, capability modules, or
distributed prose - format-agnostic).

Required components: Scope and Assumptions; Data Model; Business Process Flows;
Security and Sharing Model; Integration Architecture; Reporting and Analytics
Design; Open Decisions Log; Confidence Annotations.
Conditional components (include only if applicable to the BRD scope):
Data Migration Approach; Phasing and Delivery Plan.

For EACH component found, report: name (exactly as listed above), where
(section reference or 'distributed'), substantive_words (your count of
substantive words), design_decisions (count of distinct named design
decisions), has_specific_mechanism (true if any Salesforce mechanism is named
at module/class/pattern level), and excerpt (<=25 verbatim words).
Omit components that are entirely absent.

Return: {{"components": [{{"name": "...", "where": "...", "substantive_words": 0,
"design_decisions": 0, "has_specific_mechanism": false, "excerpt": "..."}}],
"conditional_not_applicable": ["..."]}}{JSON_ONLY}

=== SDD ({label}) ===
{_read(sdd_path)}
"""


def features_prompt(sdd_path: Path, label: str) -> str:
    return f"""List every Salesforce feature/mechanism this SDD names or relies on
(automation, security, integration, UI, data, AI, tooling) - including CURRENT
features it recommends. One entry per distinct feature.
Return: {{"features": [{{"name": "...", "section": "...", "quote": "<=20 verbatim words"}}]}}{JSON_ONLY}

=== SDD ({label}) ===
{_read(sdd_path)}
"""


def pass_prompt(*, run_id: str, label: str, dim_group: str, pass_n: int,
                sdd_path: Path, slice_path: Path, playbook_path: Path,
                core_ref: Path, dims_ref: Path, plan: dict,
                mapping_digest: dict, release_digest: dict) -> str:
    dims = [d.strip() for d in dim_group.split("-")]
    return f"""You are ONE INDEPENDENT SCORING PASS (pass {pass_n} of 5) of the Zennify W2
Section D evaluator, scoring lane "{label}" on dimensions {dims[0]}-{dims[1]}
against the frozen ZMS calibration. You have NO knowledge of any other pass and
NO knowledge of which methodology produced this SDD. Never use the tokens
ZenAgent/ZennAgent/ZA/off-the-shelf/OTS anywhere in your output.

Follow the scoring discipline and the SA reasoning playbook below. Truth-source
firewall: the operator BRD owns requirements; ZMS is the calibration bar only -
never write "ZMS requires/states/specifies/mandates". Score substance, not
length or polish. Reset between criteria.

PASS PLAN (score criteria in exactly this order; adopt the framing):
{json.dumps(plan, indent=1)}

For EVERY criterion in the calibration slice: code it Present/Partial/Absent/NA
against its depth_indicator_components, with a VERBATIM <=25-word evidence
anchor copied exactly from the SDD (or "topic absent from SDD" for Absent), the
SDD section ref, and the component names present/partial/absent. Then derive
each sub-criterion score (0..max, one decimal allowed) and each dimension score.
Content-mapping context: {json.dumps(mapping_digest)}
Release-currency context (already deducted downstream; score Dim 3 net of
these): {json.dumps(release_digest)}

Return:
{{"dim_scores": {{"{dims[0]}": 0.0, ...}},
 "sub_scores": {{"<dim>": {{"<sub_key>": 0.0}}}},
 "verdicts": {{"<zms_criterion_id>": {{"verdict": "Present|Partial|Absent|NA",
   "evidence_anchor": "<verbatim from SDD>", "sdd_ref": "...",
   "components_present": [], "components_partial": [], "components_absent": []}}}}}}
Use the exact sub_criterion keys from the scoring reference.{JSON_ONLY}

=== SCORING DISCIPLINE (section-d-core) ===
{_read(core_ref)}
=== DIMENSION REFERENCE ===
{_read(dims_ref)}
=== SA REASONING PLAYBOOK ===
{_read(playbook_path)}
=== ZMS CALIBRATION SLICE (dims {dim_group}) ===
{_read(slice_path)}
=== SDD ({label}) ===
{_read(sdd_path)}
"""


def narrative_prompt(*, label: str, aggregate: dict, coding_digest: dict,
                     brd_path: Path) -> str:
    return f"""You are writing the per-dimension narrative layer for lane "{label}" of a
blinded W2 scoring bundle. Never use ZenAgent/ZennAgent/ZA/off-the-shelf/OTS.
Ground every sentence in the aggregate results and coding below. The operator
BRD owns requirements: on dims 1, 2 and 6 cite at least one BRD reference
(story IDs like SF-1/US-2, or "BRD section N"). Never write "ZMS
requires/states/specifies/mandates" - ZMS is the calibration bar only.

For each dimension 1..7 produce:
- key_reasoning: 2-3 sentences naming the decisive ZMS criteria (by id) and,
  for dims 1/2/6, a BRD reference.
- narrative: 1-2 sentences for the report reader.
- citations: 1-3 entries, each {{"zms_criterion_id": "...", "source_label":
  "<from the coding>", "brd_ref": "...", "sdd_ref": "...", "verdict": "...",
  "evidence_anchor": "<the coding's verbatim anchor>",
  "observation": ">=30 chars of calibration observation"}}.

Return: {{"per_dim_key_reasoning": {{"1": "..."}}, "narrative_per_dim": {{"1": "..."}},
 "zms_calibration_citations": {{"1": [ ... ], ...}}}}{JSON_ONLY}

=== AGGREGATE (five-pass) ===
{_json_fit(aggregate, 6000)}
=== CODING DIGEST (modal verdicts + anchors) ===
{_json_fit(coding_digest, 12000)}
=== OPERATOR BRD ===
{_read(brd_path, 20000)}
"""


def exec_narrative_prompt(reveal_digest: dict) -> str:
    return f"""Write the executive narrative for the W2 Diagnostic Report, grounded ONLY in
this run's revealed results below (real dimensions, scores, mechanisms - no
generic filler). Plain professional prose, no em dashes.
Return: {{"exec_narrative": {{"what_we_evaluated": "...", "the_verdict": "...",
 "where_paid_off": "...", "where_trailed": "...", "release_currency": "...",
 "confidence_caveats": "...", "what_next": "..."}}}}{JSON_ONLY}

=== REVEALED RUN DIGEST ===
{json.dumps(reveal_digest, indent=1)}
"""


def review_prompt(*, dim_group: str, sdd_path: Path, slice_path: Path,
                  playbook_path: Path, brd_path: Path, release_digest: dict) -> str:
    return f"""You are the Mode B (single-SDD qualitative review) evaluator for dimensions
{dim_group}, reading the SDD against the ZMS senior-SA calibration AS A LENS
(no scoring). Every finding must be grounded: a verbatim evidence_anchor from
the SDD, or negative_evidence stating what was searched. Every recommendation
must trace to a finding and carry what_to_change / why_it_matters /
what_good_looks_like / done_when. Platform-currentness findings must cite a
salesforce.com source or carry requires=SA_CONFIRMATION_REQUIRED. No owner
fields.
Release-currency context: {json.dumps(release_digest)}

Return: {{"findings": [{{"id": "F-<dim><n>", "dimension": <int>, "zms_lens": "<criterion id>",
 "verdict": "strength|gap|risk", "evidence_anchor": "..." , "negative_evidence": null,
 "is_blocking": false, "requires": null, "brd_ref": null, "salesforce_source": null}}],
 "recommendations": [{{"id": "R-<n>", "traces_to_finding": "F-...", "what_to_change": "...",
 "why_it_matters": "...", "what_good_looks_like": "...", "done_when": "...",
 "priority": "High|Medium|Low", "affected_zms_refs": ["..."], "evidence_refs": ["..."]}}],
 "clarifications": []}}{JSON_ONLY}

=== SA REASONING PLAYBOOK ===
{_read(playbook_path)}
=== ZMS CALIBRATION SLICE (dims {dim_group}) ===
{_read(slice_path)}
=== OPERATOR BRD ===
{_read(brd_path, 20000)}
=== SDD ===
{_read(sdd_path)}
"""


def evidence_prompt(queries: list[dict], lane: str) -> str:
    return f"""You have web access. For EACH query below, run the web searches and collect
release-currency evidence for the named Salesforce mechanism. Only results from
Salesforce-controlled domains (*.salesforce.com) can assert a status; capture
title + snippet + URL exactly as retrieved. Do not invent URLs or statuses.
Return: {{"lane": "{lane}", "as_of": "<today YYYY-MM-DD>", "evidence": {{
 "<mechanism_key>": [{{"url": "...", "title": "...", "snippet": "...", "as_of": "<date>"}}]}}}}{JSON_ONLY}

=== QUERIES ===
{json.dumps(queries, indent=1)}
"""
