"""Deterministic mock intelligence for the W2 runner (--engine mock).

Produces schema-correct, R1-R25-survivable packet results with ZERO model
calls, by reading the same materials the real evaluator would (the packet
prompt embeds the calibration slice and the SDD). Verdicts come from a simple
keyword-coverage heuristic; anchors are VERBATIM SDD sentences so the R25
groundedness check passes honestly. This engine exists for demos, CI, and
pipeline development — its judgments are placeholders, not evaluations.
"""
from __future__ import annotations
import hashlib
import json
import re

SUB_BY_PARENT = {
    "1A": "requirement_parsing_depth", "1B": "stakeholder_persona_recognition",
    "1C": "constraint_assumption_extraction",
    "2A": "functional_requirement_traceability", "2B": "nfr_coverage",
    "2C": "gap_risk_identification",
    "3A": "cloud_module_selection", "3B": "trusted_design", "3C": "easy_design",
    "3D": "adaptable_design", "3E": "multi_cloud_architecture",
    "4A": "component_presence", "4B": "architectural_decision_quality",
    "5A": "dependency_id_classification", "5B": "assumption_documentation",
    "5C": "integration_failure_modes",
    "6A": "in_out_delineation", "6B": "phasing_prioritisation",
    "6C": "scope_creep_resistance",
    "7A": "estimable_work_units", "7B": "complexity_effort_indicators",
    "7C": "delivery_readiness_signals",
}
SUB_MAX = {"requirement_parsing_depth": 5, "stakeholder_persona_recognition": 5,
           "constraint_assumption_extraction": 5, "functional_requirement_traceability": 5,
           "nfr_coverage": 5, "gap_risk_identification": 5, "cloud_module_selection": 5,
           "trusted_design": 5, "easy_design": 5, "adaptable_design": 5,
           "component_presence": 9, "architectural_decision_quality": 6,
           "dependency_id_classification": 4, "assumption_documentation": 3,
           "integration_failure_modes": 3, "in_out_delineation": 4,
           "phasing_prioritisation": 3, "scope_creep_resistance": 3,
           "estimable_work_units": 5, "complexity_effort_indicators": 5,
           "delivery_readiness_signals": 5}

REQUIRED_COMPONENTS = {
    "Scope and Assumptions": ("scope", "assumption"),
    "Data Model": ("data model", "object", "field"),
    "Business Process Flows": ("process", "flow", "workflow"),
    "Security and Sharing Model": ("security", "sharing", "permission", "profile"),
    "Integration Architecture": ("integration", "api", "middleware"),
    "Reporting and Analytics Design": ("report", "analytics", "dashboard"),
    "Open Decisions Log": ("open decision", "decision log", "tbd"),
    "Confidence Annotations": ("confidence", "risk level", "certainty"),
}
SF_FEATURES = ["Flow", "Process Builder", "Workflow Rule", "Apex", "Apex Trigger",
               "Lightning Web Component", "LWC", "Aura", "Visualforce",
               "Platform Event", "REST API", "SOAP API", "Bulk API", "OmniStudio",
               "Experience Cloud", "Permission Set", "Sharing Rule", "OWD",
               "Custom Metadata", "Big Object", "Einstein", "Agentforce",
               "Data Cloud", "Dynamic Forms", "Salesforce Connect", "MuleSoft"]


def _section(prompt: str, header: str) -> str:
    m = re.search(rf"^=== {re.escape(header)}.*?===\n(.*?)(?=^=== |\Z)",
                  prompt, re.S | re.M)
    return m.group(1) if m else ""


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n{2,}", text)
            if 8 <= len(s.strip().split()) <= 40]


def _seed(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def _anchor(sdd: str, keywords: list[str]) -> tuple[str, str]:
    """Return an EXACT substring of the SDD (<=24 words) containing a keyword,
    so R25b's source-index grounding check passes honestly."""
    low = sdd.lower()
    # Mirrors the validator's _has_concrete_grounding contract (R25) exactly:
    # case-SENSITIVE structural signals + case-insensitive platform terms.
    STRUCT = re.compile(r"\d|\w+__[cr]\b|\b[A-Z][a-z]+[A-Z]\w+\b|\b\w+_\w+\b|[\"']")
    TERMS = re.compile(
        r"\b(flow|apex|trigger|platform event|owd|sharing rule|named credential|"
        r"experience cloud|shield|record-triggered|picklist|master-detail|lookup|"
        r"validation rule|permission set|profile|queue|mulesoft|oauth|rest|soap|"
        r"data cloud|lwc|aura|workflow|process builder|custom object|custom field|"
        r"record type|sales cloud|service cloud|encrypt|sso|saml|jwt|connected app|"
        r"big object|external object|change data capture|bulk api|metadata api|"
        r"integration|object|field|sharing|role hierarchy|automation)\b", re.I)
    def _concrete(s): return bool(STRUCT.search(s) or TERMS.search(s))
    positions = [m.start() for kw in keywords for m in
                 re.finditer(re.escape(kw.lower()), low)][:24]
    for i in positions:
        if True:
            start = max(sdd.rfind("\n", 0, i) + 1, sdd.rfind(". ", 0, i) + 2, 0)
            end = sdd.find(".", i)
            end = end if end > 0 else min(i + 160, len(sdd))
            raw = sdd[start:end].strip().lstrip("#*-|0123456789. ").strip()
            # cut at the 24th word boundary WITHOUT re-joining (preserve spacing)
            count, cut = 0, len(raw)
            for m in re.finditer(r"\S+", raw):
                count += 1
                if count == 24:
                    cut = m.end(); break
            anchor = raw[:cut].strip()
            # single-line only: the R25b source index resolves per line, so a
            # window spanning a newline would be a fabricated-looking quote
            if len(anchor) >= 20 and "\n" not in anchor and anchor in sdd:
                words = anchor.lower().split()
                repetitive = max(map(words.count, set(words))) / len(words) > 0.25
                if _concrete(anchor) and not repetitive:
                    return anchor, _nearest_heading(sdd, i)
                # non-concrete anchors are never acceptable for Present/Partial
    # Prefer a numbered heading (concrete by construction) over vague body text.
    for m in re.finditer(r"^(#+\s*\d[^\n]{15,80}|\d+\.\d*\s+[^\n]{12,80})$", sdd, re.M):
        h = m.group(0).strip()
        if h in sdd and len(h.lstrip('# ').strip()) >= 20:
            return h, _nearest_heading(sdd, m.start())
    return ("", "")


def _nearest_heading(sdd: str, pos: int) -> str:
    head = "SDD body"
    for m in re.finditer(r"^#+\s*(.+)$|^(\d+\.\s+.+)$", sdd[:pos], re.M):
        head = (m.group(1) or m.group(2)).strip()
    return head[:60]


# ------------------------------------------------------------------ handlers
def components(packet: dict) -> dict:
    label = packet["label"]
    sdd = _section(packet["prompt"], f"SDD ({label})") or _section(packet["prompt"], "SDD")
    low = sdd.lower()
    out, na = [], []
    for name, kws in REQUIRED_COMPONENTS.items():
        hits = [k for k in kws if k in low]
        if not hits:
            continue
        anchor, where = _anchor(sdd, hits)
        idx = low.find(hits[0])
        chunk = sdd[idx:idx + 2500]
        out.append({"name": name, "where": where or "distributed",
                    "substantive_words": max(60, len(chunk.split())),
                    "design_decisions": min(4, 1 + chunk.lower().count("we will")
                                            + chunk.lower().count("decision")),
                    "has_specific_mechanism": any(f.lower() in low for f in
                                                  ("apex", "flow", "lwc", "object")),
                    "excerpt": anchor})
    if "migration" not in low:
        na.append("Data Migration Approach")
    if "phase" not in low:
        na.append("Phasing and Delivery Plan")
    return {"components": out, "conditional_not_applicable": na}


def features(packet: dict) -> dict:
    label = packet["label"]
    sdd = _section(packet["prompt"], f"SDD ({label})") or _section(packet["prompt"], "SDD")
    found = []
    for f in SF_FEATURES:
        if re.search(rf"\b{re.escape(f)}s?\b", sdd, re.I):
            anchor, where = _anchor(sdd, [f])
            found.append({"name": f, "section": where, "quote": anchor[:120]})
    return {"features": found}


def _verdict_for(crit: dict, sdd: str, jitter: int) -> dict:
    comps = crit.get("depth_indicator_components") or [crit.get("depth_indicator", "")]
    low = sdd.lower()
    present, partial, absent = [], [], []
    for comp in comps:
        words = [w for w in re.findall(r"[a-zA-Z]{5,}", comp.lower())
                 if w not in ("named", "each", "where", "their", "which", "these")]
        hits = sum(1 for w in set(words[:6]) if w in low)
        (present if hits >= 2 else partial if hits == 1 else absent).append(comp)
    if jitter % 7 == 0 and present:      # small deterministic pass-to-pass wobble
        partial.append(present.pop())
    verdict = ("Present" if len(present) >= max(1, len(comps) - len(comps) // 3)
               and not absent else "Partial" if present or partial else "Absent")
    kw = re.findall(r"[a-zA-Z]{5,}", " ".join(present + partial))[:8] or \
        re.findall(r"[a-zA-Z]{5,}", crit.get("name", ""))
    anchor, sdd_ref = _anchor(sdd, kw)
    # R25e: a Present/Partial anchor must textually touch >=1 depth component
    # content word (>3 chars). If the chosen slice does not, retry per-component;
    # if nothing relevant exists in the SDD, the honest verdict is Absent.
    def _relevant(a: str) -> bool:
        # EXACT replica of evidence_anchor_verify.supports_verdict tokenization:
        # lowercase, whitespace-collapse, split, keep punctuation, len > 3.
        na = re.sub(r"\s+", " ", a.lower()).strip()
        for c in comps:
            cw = [w for w in re.sub(r"\s+", " ", str(c).lower()).split() if len(w) > 3]
            if cw and any(w in na for w in cw):
                return True
        return False
    if verdict != "Absent" and anchor and not _relevant(anchor):
        for c in comps:
            cand, ref = _anchor(sdd, re.findall(r"[a-zA-Z]{4,}", str(c))[:6])
            if cand and _relevant(cand):
                anchor, sdd_ref = cand, ref
                break
        else:
            anchor = ""
    if verdict != "Absent" and len(anchor) < 20:
        verdict, anchor = "Absent", ""
    return {"verdict": verdict,
            "evidence_anchor": anchor if verdict != "Absent" else "topic absent from SDD",
            "sdd_ref": sdd_ref or "n/a",
            "components_present": present, "components_partial": partial,
            "components_absent": absent}


DIVERGENCE_PCT = 15   # ~15% of criteria differ by judge in dual-judge mode (T-5)


def _dual_ctx(packet: dict) -> tuple[bool, str, str]:
    """(is_dual, judge, base_pid): dual-judge packets carry meta.judge and a
    judge-suffixed packet id. base_pid strips the judge so BOTH judges derive
    the same baseline verdicts — the seeded divergence is then applied as a
    deterministic perturbation on the gemini side only."""
    meta = packet.get("meta") or {}
    judge = meta.get("judge")
    pid = packet.get("packet_id", "")
    if judge and pid.endswith(":" + judge):
        return True, judge, pid.rsplit(":", 1)[0]
    return False, judge or "claude-code", pid


def _perturb_verdict(rec: dict, crit: dict, sdd: str) -> dict:
    """Deterministic gemini-side disagreement (T-5 seeded divergence): shift
    the verdict one step and re-anchor, keeping the result schema-correct and
    R25-survivable (anchors stay verbatim SDD slices)."""
    out = dict(rec)
    v = rec.get("verdict")
    if v == "Present":
        out["verdict"] = "Partial"
        if out.get("components_present"):
            moved = out["components_present"][-1]
            out["components_present"] = out["components_present"][:-1]
            out["components_partial"] = list(out.get("components_partial", [])) + [moved]
    elif v == "Partial":
        out["verdict"] = "Absent"
        out["evidence_anchor"] = "topic absent from SDD"
        out["components_absent"] = sorted(set(
            list(out.get("components_absent", []))
            + list(out.get("components_partial", []))))
        out["components_partial"] = []
    elif v == "Absent":
        # Absent -> Partial needs a genuine anchor; if the SDD offers none,
        # the honest perturbation is no perturbation.
        kw = re.findall(r"[a-zA-Z]{5,}", crit.get("name", ""))[:6]
        anchor, ref = _anchor(sdd, kw)
        if anchor:
            out["verdict"] = "Partial"
            out["evidence_anchor"] = anchor
            out["sdd_ref"] = ref or out.get("sdd_ref") or "SDD body"
            if out.get("components_absent"):
                moved = out["components_absent"][-1]
                out["components_absent"] = out["components_absent"][:-1]
                out["components_partial"] = list(out.get("components_partial", [])) + [moved]
    return out


def scoring_pass(packet: dict) -> dict:
    meta = packet.get("meta") or {}
    label, group, n = packet["label"], meta.get("dim_group", "1-3"), int(meta.get("pass_n", 1) or 1)
    dual, judge, base_pid = _dual_ctx(packet)
    prompt = packet["prompt"]
    sdd = _section(prompt, f"SDD ({label})") or _section(prompt, "SDD")
    slice_txt = _section(prompt, f"ZMS CALIBRATION SLICE (dims {group})")
    crits = json.loads(slice_txt).get("criteria") or json.loads(slice_txt).get(
        "applicable_criteria", [])
    floor_cap = (meta.get("floor_cap") if meta.get("floor_cap") is not None
                 else None)
    rr = abs(float(meta.get("rr_capped_total") or 0))

    verdicts, per_sub_scoreable = {}, {}
    for idx, c in enumerate(crits):
        # Seed on the JUDGE-NEUTRAL packet id so both judges share a baseline;
        # divergence is then a deliberate gemini-side perturbation.
        j = _seed(base_pid, c["id"]) + n
        rec = _verdict_for(c, sdd, j)
        if dual and judge == "gemini":
            forced_first = (idx == 0)  # >=1 guaranteed divergence per group
            seeded = _seed("divergence", base_pid, c["id"]) % 100 < DIVERGENCE_PCT
            if forced_first or seeded:
                rec = _perturb_verdict(rec, c, sdd)
        verdicts[c["id"]] = rec
        sub = SUB_BY_PARENT.get(c.get("parent_sub_criterion", ""), None)
        if sub:
            score = {"Present": 1.0, "Partial": 0.55, "Absent": 0.1}.get(rec["verdict"], 0)
            per_sub_scoreable.setdefault(sub, []).append(score)

    dims = [str(d) for d in range(int(group[0]), int(group[-1]) + 1)]
    sub_scores, dim_scores = {}, {}
    for d in dims:
        subs = {k: v for k, v in SUB_BY_PARENT.items() if k.startswith(d)}
        ss = {}
        for parent, sub in subs.items():
            if sub == "multi_cloud_architecture":
                continue
            cov = per_sub_scoreable.get(sub)
            base = (sum(cov) / len(cov)) if cov else 0.72
            wob_seed = (_seed(label, group, sub, judge) if dual
                        else _seed(label, group, sub, n))
            wob = ((wob_seed % 9) - 4) / 100.0
            ss[sub] = round(max(0.0, min(1.0, base + wob)) * SUB_MAX[sub], 1)
        raw = round(sum(ss.values()), 1)
        if not dual:
            # five-pass legacy convention: the pass reports NET dim scores.
            # Dual-judge judges report RAW scores; the engine nets/floors once
            # post-merge (TR-14) — mirroring the v2.0 pass prompt exactly.
            if d == "3" and rr:
                net = max(0.0, raw - rr)
                scale = (net / raw) if raw else 0
                ss = {k: round(v * scale, 1) for k, v in ss.items()}
                raw = round(sum(ss.values()), 1)
            if d == "4" and floor_cap is not None and raw > floor_cap:
                scale = floor_cap / raw
                ss = {k: round(v * scale, 1) for k, v in ss.items()}
                raw = round(sum(ss.values()), 1)
        sub_scores[d] = ss
        dim_scores[d] = raw
    return {"dim_scores": dim_scores, "sub_scores": sub_scores, "verdicts": verdicts}


def reconcile(packet: dict) -> dict:
    """Reconciliation handler (T-5): evidence-cited rulings over the divergent
    items. The FIRST divergent criterion (sorted) returns `dissent` — the
    forced, deterministic >=1 dissent per run the smoke asserts — and every
    other item is ruled with a verbatim SDD citation that survives R25."""
    prompt = packet["prompt"]
    label = packet.get("label", "Output A")
    sdd = _section(prompt, f"SDD ({label})") or _section(prompt, "SDD")

    def _first_json(text: str) -> dict:
        """Parse the first balanced JSON object in a section — robust to any
        trailing prose that shares the section (raw_decode, not loads)."""
        t = (text or "").strip()
        if not t.startswith("{"):
            i = t.find("{")
            if i < 0:
                return {}
            t = t[i:]
        try:
            obj, _ = json.JSONDecoder().raw_decode(t)
            return obj if isinstance(obj, dict) else {}
        except json.JSONDecodeError:
            return {}

    crit_items = _first_json(_section(prompt, "VERDICT ITEMS"))
    sub_items = _first_json(_section(prompt, "SCORE ITEMS"))
    order = {"Present": 3, "Partial": 2, "Absent": 1, "NA": 0,
             "risk": 3, "gap": 2, "strength": 1}

    def _sdd_citation(*cands) -> str:
        for cand in cands:
            if isinstance(cand, str) and len(cand) >= 20 and cand in sdd:
                return cand
        anchor, _ = _anchor(sdd, ["integration", "apex", "flow", "sharing", "object"])
        return anchor

    rulings = {}
    for i, key in enumerate(sorted(crit_items)):
        pair = crit_items[key] or {}
        ea = pair.get("claude-code") or {}
        eb = pair.get("gemini") or {}
        va, vb = ea.get("verdict", ""), eb.get("verdict", "")
        if i == 0:
            rulings[key] = {
                "ruling": "dissent", "value": None, "citation": None,
                "rationale": ("Both readings are genuinely supported by the "
                              "cited passages; no single quote settles the "
                              "depth question for this criterion.")}
            continue
        # adopt the side whose claim is STRONGER when its anchor genuinely
        # resolves in the SDD; otherwise adopt the other side.
        stronger_is_a = order.get(va, 0) >= order.get(vb, 0)
        first, second = ((ea, "adopt_claude"), (eb, "adopt_gemini")) if stronger_is_a \
            else ((eb, "adopt_gemini"), (ea, "adopt_claude"))
        pick, ruling = first
        anchor = pick.get("evidence_anchor", "")
        if not (isinstance(anchor, str) and len(anchor) >= 20 and anchor in sdd):
            pick, ruling = second
        citation = _sdd_citation(pick.get("evidence_anchor", ""),
                                 ea.get("evidence_anchor", ""),
                                 eb.get("evidence_anchor", ""))
        rulings[key] = {
            "ruling": ruling, "value": None, "citation": citation,
            "rationale": ("The cited passage substantiates this reading of the "
                          "depth components against the calibration bar.")}
    for key in sorted(sub_items):
        item = sub_items[key] or {}
        sa, sb = item.get("claude-code"), item.get("gemini")
        nums = [x for x in (sa, sb) if isinstance(x, (int, float))]
        if len(nums) == 2:
            mid = round((nums[0] + nums[1]) / 2.0, 1)
            rulings[key] = {
                "ruling": "meet_between", "value": {"score": mid},
                "citation": _sdd_citation(),
                "rationale": ("The evidence supports depth between the two "
                              "readings; the cited passage anchors the midpoint.")}
        else:
            ruling = "adopt_claude" if isinstance(sa, (int, float)) else "adopt_gemini"
            rulings[key] = {
                "ruling": ruling, "value": None, "citation": _sdd_citation(),
                "rationale": "Only one judge produced a score for this sub-criterion."}
    return {"rulings": rulings}


def narrative(packet: dict) -> dict:
    prompt = packet["prompt"]
    agg = json.loads(_section(prompt, "AGGREGATE (five-pass)") or "{}")
    coding = json.loads(_section(prompt, "CODING DIGEST (modal verdicts + anchors)") or "{}")
    brd = _section(prompt, "OPERATOR BRD")
    story = (re.search(r"\b(SF-\d+|US-\d+|STORY-\d+)\b", brd) or [None])
    brd_ref = story.group(1) if hasattr(story, "group") else "BRD section 1"
    by_dim: dict[str, list] = {str(d): [] for d in range(1, 8)}
    for cid, rec in coding.items():
        by_dim.setdefault(cid[0], []).append((cid, rec))
    kr, npd, cits = {}, {}, {}
    for d in map(str, range(1, 8)):
        entries = by_dim.get(d, [])[:3]
        mean = (agg.get("per_dim_mean") or {}).get(d, 0)
        cit_list = []
        for cid, rec in entries:
            anchor = rec.get("evidence_anchor") or "topic absent from SDD"
            v = rec.get("verdict") or "Partial"
            entry = {
                "zms_criterion_id": cid, "source_label": "Zennify SDD standard",
                "brd_ref": brd_ref, "sdd_ref": rec.get("sdd_ref") or "SDD body",
                "verdict": v, "evidence_anchor": anchor,
                "observation": (f"Against the calibration bar, {cid} coded {v}: the "
                                f"design {'demonstrates' if v == 'Present' else 'only partially demonstrates' if v == 'Partial' else 'does not evidence'} "
                                "the expected depth components in the cited passage."),
            }
            if v == "Absent":
                entry["negative_evidence"] = {
                    "searched_sections": ["full document", rec.get("sdd_ref") or "all headings"],
                    "searched_terms": re.findall(r"[a-zA-Z]{5,}", cid)[:4] or [cid]}
            cit_list.append(entry)
        ids = ", ".join(c["zms_criterion_id"] for c in cit_list) or "the applicable criteria"
        obs_tail = (" Calibration note: " + cit_list[0]["observation"][:90]) if cit_list else ""
        brd_bit = (f" Requirements grounding: {brd_ref} and BRD section 1 anchor the "
                   "coverage read." if d in ("1", "2", "6") else "")
        kr[d] = (f"Five-pass mean {mean}: the decisive calibration comparisons were {ids}, "
                 f"where the coding above shows the demonstrated depth components against "
                 f"the calibration bar.{brd_bit}{obs_tail}")
        npd[d] = (f"Dimension {d} landed at {mean} on the strength of the coded evidence; "
                  "the anchors cited alongside carry the audit trail.")
        cits[d] = cit_list or [{
            "zms_criterion_id": f"{d}A.general", "source_label": "Zennify SDD standard",
            "brd_ref": brd_ref, "sdd_ref": "SDD body", "verdict": "Absent",
            "evidence_anchor": "topic absent from SDD",
            "negative_evidence": {"searched_sections": ["full document"],
                                  "searched_terms": ["dimension", d]},
            "observation": "Calibration comparison recorded without a criterion-level "
                           "coding entry for this dimension in the digest."}]
    return {"per_dim_key_reasoning": kr, "narrative_per_dim": npd,
            "zms_calibration_citations": cits}


def exec_narrative(packet: dict) -> dict:
    d = json.loads(_section(packet["prompt"], "REVEALED RUN DIGEST") or "{}")
    lm = d.get("lift_metrics") or {}
    lift = lm.get("headline_lift_output_a_minus_b")
    conc = d.get("cross_model_concurrence") or {}
    if conc:
        confidence = (f"Each lane was scored once by each of two independent model "
                      f"families from identical blinded packets; cross-model agreement "
                      f"{conc.get('agreement_overall', 'n/a')} and the inter-judge lift "
                      "band qualify the headline number. Dissents were resolved "
                      "conservatively and are preserved in the annex.")
    else:
        confidence = ("Five independent scoring passes per lane; variance flags "
                      "and the correlation-adjusted band qualify the headline number.")
    return {"exec_narrative": {
        "what_we_evaluated": "Two solution designs for the same BRD, scored blind across "
                             "the seven W2 dimensions against the frozen ZMS calibration.",
        "the_verdict": f"The blinded lane difference was {lift} points on the 100-point "
                       "scale; the reveal orients it as the methodology lift.",
        "where_paid_off": "The stronger lane led on the dimensions with the largest "
                          "per-dimension gaps in the lift table.",
        "where_trailed": "Dimensions with negative or near-zero deltas are listed in the "
                         "per-dimension lift table for review.",
        "release_currency": "Release-currency findings and their deductions are itemised "
                            "in Appendix B with Salesforce sources.",
        "confidence_caveats": confidence,
        "what_next": "Address the prioritised refinement areas, then re-run to confirm closure.",
    }}


def review(packet: dict) -> dict:
    prompt = packet["prompt"]
    meta = packet.get("meta") or {}
    dual, judge, base_pid = _dual_ctx(packet)
    group = meta.get("dim_group") or (
        packet["packet_id"].split(":")[1]
        if packet.get("packet_id", "").count(":") >= 1 else "1-3")
    sdd = _section(prompt, "SDD")
    sl = json.loads(_section(prompt, f"ZMS CALIBRATION SLICE (dims {group})") or "{}")
    crits = sl.get("criteria") or sl.get("applicable_criteria") or []
    findings, recs = [], []
    for i, c in enumerate(crits, 1):
        rec = _verdict_for(c, sdd, i)
        fid = f"F-{group.replace('-', '')}{i:02d}"
        verdict = {"Present": "strength", "Partial": "gap", "Absent": "gap"}[
            rec["verdict"]] if rec["verdict"] != "NA" else "gap"
        if dual and judge == "gemini":
            # Seeded divergence for Mode B (T-5), applied in the FINDING
            # verdict space (strength/gap/risk) — a Partial->Absent shift is
            # invisible there (both map to gap), so perturb the finding
            # verdict itself: first criterion always (guaranteed >=1
            # divergent lens per group), ~15% elsewhere.
            if i == 1 or _seed("divergence", base_pid, c["id"]) % 100 < DIVERGENCE_PCT:
                verdict = {"strength": "gap", "gap": "risk", "risk": "gap"}[verdict]
        f = {"id": fid, "dimension": c.get("dimension", int(group[0])),
             "zms_lens": c["id"], "verdict": verdict, "is_blocking": False,
             "requires": None, "brd_ref": None, "salesforce_source": None}
        if rec["verdict"] == "Absent":
            f["negative_evidence"] = ("topic absent from SDD; searched the full document "
                                      f"for {', '.join(rec['components_absent'][:2])[:80]}")
        else:
            f["evidence_anchor"] = rec["evidence_anchor"]
        findings.append(f)
        if verdict in ("gap", "risk") and len(recs) < 8:
            recs.append({
                "id": f"R-{len(recs)+1:02d}", "traces_to_finding": fid,
                "what_to_change": f"Add the missing depth for {c.get('name', c['id'])} "
                                  f"({', '.join((rec['components_absent'] + rec['components_partial'])[:2])[:100]}).",
                "why_it_matters": f"The calibration bar ({c['id']}) expects this depth "
                                  "before the design is estimable and buildable.",
                "what_good_looks_like": c.get("depth_indicator", "")[:200]
                                        or "The depth indicator satisfied in full.",
                "done_when": "The SDD names the concrete artefacts and the coding for "
                             "this criterion would read Present.",
                "priority": "High" if rec["verdict"] == "Absent" else "Medium",
                "affected_zms_refs": [c["id"]], "evidence_refs": [fid]})
    return {"findings": findings, "recommendations": recs, "clarifications": []}


def evidence(packet: dict) -> dict:
    return {"lane": packet["label"][-1], "as_of": None, "evidence": {}}


HANDLERS = {"components": components, "features": features, "pass": scoring_pass,
            "narrative": narrative, "exec_narrative": exec_narrative,
            "review": review, "evidence": evidence, "reconcile": reconcile}


def execute(packet: dict) -> dict:
    return HANDLERS[packet["kind"]](packet)


def usage_for(packet: dict) -> dict:
    """Mock usage ledger entry. Reports the judge the packet was ADDRESSED to,
    so the server's TR-8 provenance check exercises the same path it guards
    for real runners. Zero cost, zero tokens — no model was called."""
    meta = packet.get("meta") or {}
    return {"engine": "mock", "judge": meta.get("judge") or "claude-code",
            "model": "mock", "input_tokens": 0, "output_tokens": 0,
            "total_cost_usd": 0.0}
