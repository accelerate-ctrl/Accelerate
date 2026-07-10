"""Autonomous judge — the app scores on its own, no AI judges required.

Screening-grade evaluation for runs created with evaluator_model
"autonomous": every packet the pipeline stages is executed IN-PROCESS by a
deterministic scorer built on the pre-intelligence layer (evidence locator,
synonym-expanded component matching, mechanism lexicon). No Claude, no
Gemini, no runner, no credentials, zero model calls.

Honesty contract:
- Two genuinely different scoring philosophies fill the two judge slots —
  slot "claude-code" runs the EVIDENCE-primary screener, slot "gemini" the
  stricter COVERAGE-primary screener — so the consensus/diff/reconcile
  machinery operates on real methodological disagreement, not theater.
  usage.engine records "auto-screener" on every packet; the run record keeps
  evaluator_model="autonomous"; nothing claims an AI judged.
- Anchors are verbatim single-line SDD slices (the same R25-proof extractor
  the mock engine uses); a verdict that cannot cite relevant text degrades
  to Absent rather than fabricate.
- This is SCREENING, not judgment: lexical/statistical pattern recognition
  against the calibration language. It cannot weigh design quality the way
  the dual AI panel does — reports disclose the mode.
"""
from __future__ import annotations
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "runner"))
import mock_intelligence as base  # shape templates + R25-proof anchor extractor

from nlp.doc_model import build_doc_model
from nlp.evidence_locator import SYNONYMS, locate_candidates
from nlp.lexicon import find_mechanisms
from nlp.textproc import content_terms

def _concrete(anchor: str) -> bool:
    """R25's own concreteness contract (score_sheet_populate) — imported so
    the screener can never drift from what validation will enforce."""
    if not anchor or len(anchor) < 20:
        return False
    try:
        from score_sheet_populate import _has_concrete_grounding
        return bool(_has_concrete_grounding(anchor))
    except Exception:
        import re as _re
        return bool(_re.search(r"\d|\w+__[cr]\b|\b[A-Z][a-z]+[A-Z]\w+\b|\b\w+_\w+\b|[\"']", anchor))


RUNNER_ID = "auto-screener"
ENGINE = "auto-screener"
MODEL = "deterministic-nlp-preintel"

# ---- calibrated thresholds (learning loop 1) -------------------------------
# Defaults reproduce the gold-verified v1 behavior. A fitted params.json
# (written ONLY after passing the gold-corpus gate in server/learning.py)
# overrides them; W2_SCREENER_PARAMS env carries candidate params during
# gating. invalidate_params() forces a reload after an update.
_DEFAULT_PARAMS = {"min_matched_terms": 2, "present_deficit_div": 3}
_params_cache: dict | None = None


def _params_path():
    import os
    d = os.environ.get("W2APP_DATA")
    return Path(d) / "learning" / "params.json" if d else None


def invalidate_params() -> None:
    global _params_cache
    _params_cache = None


def get_params() -> dict:
    global _params_cache
    if _params_cache is not None:
        return _params_cache
    import os
    p = dict(_DEFAULT_PARAMS)
    pp = _params_path()
    try:
        if pp and pp.exists():
            saved = json.loads(pp.read_text())
            p.update({k: int(saved[k]) for k in _DEFAULT_PARAMS if k in saved})
    except Exception:
        pass
    env = os.environ.get("W2_SCREENER_PARAMS")
    if env:
        try:
            cand = json.loads(env)
            p.update({k: int(cand[k]) for k in _DEFAULT_PARAMS if k in cand})
        except Exception:
            pass
        return p  # candidate params are transient: never cached
    _params_cache = p
    return p


# ------------------------------------------------------------- verdict core
def _expand(terms: set[str]) -> set[str]:
    out = set(terms)
    for t in terms:
        out.update(SYNONYMS.get(t, ()))
    return out


def _sentence_terms(sdd: str) -> list[set[str]]:
    doc = build_doc_model(sdd)
    out = []
    for sec in doc["sections"]:
        for s in sec["sentences"]:
            ts = content_terms(s)
            if ts:
                out.append(ts)
    return out


# Terms too generic to carry a single-match "partial" on their own — on a
# Salesforce SDD nearly every section touches these, so one hit proves
# nothing about THIS component's topic.
_GENERIC = frozenset({"security", "data", "system", "platform", "salesforce",
                      "design", "solution", "process", "management", "model",
                      "named", "stated", "defined", "documented"})


def _fold(ts: set[str]) -> set[str]:
    """Cheap plural folding so 'dashboards' meets 'dashboard'."""
    out = set(ts)
    for t in ts:
        if len(t) > 3 and t.endswith("s"):
            out.add(t[:-1])
        if len(t) > 4 and t.endswith("es"):
            out.add(t[:-2])
    return out


def _comp_status(comp, sent_terms: list[set[str]]) -> str:
    orig = _fold(content_terms(str(comp)))
    terms = _fold(_expand(content_terms(str(comp))))
    if not terms:
        return "absent"
    singles: set[str] = set()
    for ts in sent_terms:
        fts = _fold(ts)
        if len(terms & fts) >= 2:
            return "present"
        # single-term evidence only counts on the component's OWN words —
        # a lone synonym hit ("permission" for an AI-governance component
        # via the security expansion) proves nothing about this topic.
        singles |= (orig & fts)
    return "partial" if (singles - _GENERIC) else "absent"


def _auto_verdict(crit: dict, sdd: str, judge: str,
                  sent_terms: list[set[str]], cands: list[dict]) -> dict:
    """One criterion, one screener verdict. judge slot selects the
    philosophy: claude-code = evidence-primary, gemini = coverage-primary
    (stricter Present bar) — real divergence on borderline criteria."""
    comps = crit.get("depth_indicator_components") or [crit.get("depth_indicator", "")]
    present, partial, absent = [], [], []
    for comp in comps:
        s = _comp_status(comp, sent_terms)
        (present if s == "present" else partial if s == "partial" else absent).append(comp)
    prm = get_params()
    strong_candidate = bool(cands) and (cands[0].get("matched_terms", 0)
                                        >= prm["min_matched_terms"])
    if judge == "gemini":  # coverage-primary: every component must be present
        verdict = ("Present" if len(present) == len(comps) and strong_candidate
                   else "Partial" if present or len(partial) >= 2
                   else "Absent")
    else:                  # evidence-primary: strong evidence + majority depth
        pdd = prm["present_deficit_div"]
        verdict = ("Present" if not absent and strong_candidate
                   and len(present) >= max(1, len(comps) - len(comps) // pdd)
                   else "Partial" if present or partial else "Absent")
    kw = re.findall(r"[a-zA-Z]{5,}", " ".join(map(str, present + partial)))[:8] or \
        re.findall(r"[a-zA-Z]{5,}", crit.get("name", ""))
    anchor, sdd_ref = base._anchor(sdd, kw)

    def _relevant(a: str) -> bool:
        na = re.sub(r"\s+", " ", a.lower()).strip()
        for c in comps:
            cw = [w for w in re.sub(r"\s+", " ", str(c).lower()).split() if len(w) > 3]
            if cw and any(w in na for w in cw):
                return True
        return False

    if verdict != "Absent" and anchor and not _relevant(anchor):
        for c in comps:
            cand, ref = base._anchor(sdd, re.findall(r"[a-zA-Z]{4,}", str(c))[:6])
            if cand and _relevant(cand):
                anchor, sdd_ref = cand, ref
                break
        else:
            anchor = ""
    if verdict != "Absent" and (len(anchor) < 20 or not _concrete(anchor)):
        verdict, anchor = "Absent", ""
    return {"verdict": verdict,
            "evidence_anchor": anchor if verdict != "Absent" else "topic absent from SDD",
            "sdd_ref": sdd_ref or "n/a",
            "components_present": present, "components_partial": partial,
            "components_absent": absent}


# ---------------------------------------------------------------- handlers
def scoring_pass(packet: dict) -> dict:
    meta = packet.get("meta") or {}
    label, group = packet["label"], meta.get("dim_group", "1-3")
    judge = (meta.get("judge") or "claude-code")
    prompt = packet["prompt"]
    sdd = base._section(prompt, f"SDD ({label})") or base._section(prompt, "SDD")
    slice_txt = base._section(prompt, f"ZMS CALIBRATION SLICE (dims {group})")
    sl = json.loads(slice_txt)
    crits = sl.get("criteria") or sl.get("applicable_criteria", [])
    floor_cap = meta.get("floor_cap")
    rr = abs(float(meta.get("rr_capped_total") or 0))
    dual = bool(meta.get("judge"))

    sent_terms = _sentence_terms(sdd)
    located = locate_candidates(sdd, crits)["per_criterion"]
    verdicts, per_sub = {}, {}
    for c in crits:
        rec = _auto_verdict(c, sdd, judge, sent_terms,
                            located.get(c["id"], {}).get("candidates", []))
        verdicts[c["id"]] = rec
        sub = base.SUB_BY_PARENT.get(c.get("parent_sub_criterion", ""))
        if sub:
            score = {"Present": 1.0, "Partial": 0.55, "Absent": 0.1}[rec["verdict"]]
            per_sub.setdefault(sub, []).append(score)

    dims = [str(d) for d in range(int(group[0]), int(group[-1]) + 1)]
    sub_scores, dim_scores = {}, {}
    for d in dims:
        subs = {k: v for k, v in base.SUB_BY_PARENT.items() if k.startswith(d)}
        ss = {}
        for parent, sub in subs.items():
            if sub == "multi_cloud_architecture":
                continue
            cov = per_sub.get(sub)
            b = (sum(cov) / len(cov)) if cov else 0.55  # unscored: midline, no wobble
            ss[sub] = round(max(0.0, min(1.0, b)) * base.SUB_MAX[sub], 1)
        raw = round(sum(ss.values()), 1)
        if not dual:  # five-pass legacy convention (kept for parity)
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
    """Evidence-ruled rulings, no theater: adopt the side whose anchor
    genuinely resolves in the SDD (stronger claim first); record a dissent
    only when the readings are two steps apart AND both anchors resolve —
    the honestly-unresolvable case for a lexical screener."""
    prompt = packet["prompt"]
    label = packet.get("label", "Output A")
    sdd = base._section(prompt, f"SDD ({label})") or base._section(prompt, "SDD")

    def _first_json(text):
        t = (text or "").strip()
        i = t.find("{")
        if i < 0:
            return {}
        try:
            obj, _ = json.JSONDecoder().raw_decode(t[i:])
            return obj if isinstance(obj, dict) else {}
        except json.JSONDecodeError:
            return {}

    crit_items = _first_json(base._section(prompt, "VERDICT ITEMS"))
    sub_items = _first_json(base._section(prompt, "SCORE ITEMS"))
    order = {"Present": 3, "Partial": 2, "Absent": 1, "NA": 0,
             "risk": 3, "gap": 2, "strength": 1}

    def _resolves(a) -> bool:
        # a usable citation must resolve verbatim in the SDD AND satisfy the
        # R25 concreteness contract — a paraphrase-grade quote fails sheets.
        return (isinstance(a, str) and len(a) >= 20 and a in sdd
                and _concrete(a))

    def _cite(*cands) -> str:
        for c in cands:
            if _resolves(c):
                return c
        anchor, _ = base._anchor(sdd, ["integration", "apex", "flow", "sharing", "object"])
        return anchor if _concrete(anchor) else ""

    rulings = {}
    for key in sorted(crit_items):
        pair = crit_items[key] or {}
        ea = pair.get("claude-code") or {}
        eb = pair.get("gemini") or {}
        va, vb = ea.get("verdict", ""), eb.get("verdict", "")
        aa, ab = ea.get("evidence_anchor", ""), eb.get("evidence_anchor", "")
        if abs(order.get(va, 0) - order.get(vb, 0)) >= 2 and _resolves(aa) and _resolves(ab):
            rulings[key] = {
                "ruling": "dissent", "value": None, "citation": None,
                "rationale": ("The screeners read the same passages two steps "
                              "apart; a lexical scorer cannot settle the depth "
                              "question — preserved for human review.")}
            continue
        stronger_is_a = order.get(va, 0) >= order.get(vb, 0)
        first, second = ((ea, "adopt_claude"), (eb, "adopt_gemini")) if stronger_is_a \
            else ((eb, "adopt_gemini"), (ea, "adopt_claude"))
        pick, ruling = first
        if not _resolves(pick.get("evidence_anchor", "")):
            pick, ruling = second
        citation = _cite(pick.get("evidence_anchor", ""), aa, ab)
        if not citation and pick.get("verdict") in ("Present", "Partial"):
            # No concrete verbatim quote grounds the picked reading. The
            # honest lexical ruling is the OTHER side if it needs no anchor
            # (Absent); when both sides claim Present/Partial without a
            # groundable quote, preserve a dissent — never assert what
            # validation would reject as ungrounded.
            other = second if ruling == first[1] else first
            pick, ruling = other
            if pick.get("verdict") in ("Present", "Partial"):
                rulings[key] = {
                    "ruling": "dissent", "value": None, "citation": None,
                    "rationale": ("Neither screener can ground this reading in "
                                  "a concrete verbatim quote; preserved for "
                                  "human review rather than asserted.")}
                continue
        rulings[key] = {
            "ruling": ruling, "value": None,
            "citation": citation or None,
            "rationale": ("Adopted the reading whose cited passage resolves "
                          "verbatim in the SDD and carries the stronger "
                          "component coverage.")}
    for key in sorted(sub_items):
        item = sub_items[key] or {}
        sa, sb = item.get("claude-code"), item.get("gemini")
        nums = [x for x in (sa, sb) if isinstance(x, (int, float))]
        if len(nums) == 2:
            rulings[key] = {"ruling": "meet_between",
                            "value": {"score": round((nums[0] + nums[1]) / 2.0, 1)},
                            "citation": _cite(),
                            "rationale": ("Depth sits between the two screener "
                                          "readings; midpoint adopted conservatively.")}
        else:
            rulings[key] = {"ruling": "adopt_claude" if isinstance(sa, (int, float))
                            else "adopt_gemini", "value": None, "citation": _cite(),
                            "rationale": "Only one screener scored this sub-criterion."}
    return {"rulings": rulings}


def review(packet: dict) -> dict:
    prompt = packet["prompt"]
    meta = packet.get("meta") or {}
    judge = (meta.get("judge") or "claude-code")
    group = meta.get("dim_group") or (
        packet["packet_id"].split(":")[1]
        if packet.get("packet_id", "").count(":") >= 1 else "1-3")
    sdd = base._section(prompt, "SDD")
    sl = json.loads(base._section(prompt, f"ZMS CALIBRATION SLICE (dims {group})") or "{}")
    crits = sl.get("criteria") or sl.get("applicable_criteria") or []
    sent_terms = _sentence_terms(sdd)
    located = locate_candidates(sdd, crits)["per_criterion"]
    findings, recs = [], []
    for i, c in enumerate(crits, 1):
        rec = _auto_verdict(c, sdd, judge, sent_terms,
                            located.get(c["id"], {}).get("candidates", []))
        fid = f"F-{group.replace('-', '')}{i:02d}"
        verdict = {"Present": "strength", "Partial": "gap", "Absent": "gap"}[
            rec["verdict"]] if rec["verdict"] != "NA" else "gap"
        f = {"id": fid, "dimension": c.get("dimension", int(group[0])),
             "zms_lens": c["id"], "verdict": verdict, "is_blocking": False,
             "requires": None, "brd_ref": None, "salesforce_source": None}
        if rec["verdict"] == "Absent":
            f["negative_evidence"] = ("topic absent from SDD; searched the full document "
                                      f"for {', '.join(map(str, rec['components_absent'][:2]))[:80]}")
        else:
            f["evidence_anchor"] = rec["evidence_anchor"]
        findings.append(f)
        if verdict in ("gap", "risk") and len(recs) < 8:
            recs.append({
                "id": f"R-{len(recs)+1:02d}", "traces_to_finding": fid,
                "what_to_change": f"Add the missing depth for {c.get('name', c['id'])} "
                                  f"({', '.join(map(str, (rec['components_absent'] + rec['components_partial'])[:2]))[:100]}).",
                "why_it_matters": f"The calibration bar ({c['id']}) expects this depth "
                                  "before the design is estimable and buildable.",
                "what_good_looks_like": (c.get("depth_indicator", "") or "")[:200]
                                        or "The depth indicator satisfied in full.",
                "done_when": "The SDD names the concrete artefacts and the coding for "
                             "this criterion would read Present.",
                "priority": "High" if rec["verdict"] == "Absent" else "Medium",
                "affected_zms_refs": [c["id"]], "evidence_refs": [fid]})
    return {"findings": findings, "recommendations": recs, "clarifications": []}


def features(packet: dict) -> dict:
    label = packet["label"]
    sdd = base._section(packet["prompt"], f"SDD ({label})") or base._section(packet["prompt"], "SDD")
    out = []
    for m in find_mechanisms(build_doc_model(sdd)):
        anchor, where = base._anchor(sdd, [m["mechanism"]])
        out.append({"name": m["mechanism"], "section": where or m["section"],
                    "quote": (anchor or "")[:120]})
    return {"features": out}


def exec_narrative(packet: dict) -> dict:
    """Report-facing disclosure: never let autonomous output claim AI judged."""
    out = base.exec_narrative(packet)
    out["exec_narrative"]["confidence_caveats"] = (
        "AUTONOMOUS SCREENING MODE: both judge slots were executed by the "
        "app's deterministic screeners (evidence-primary and coverage-primary "
        "lexical scorers) — no AI model judged this run. Agreement figures "
        "measure cross-screener concurrence on term-level evidence. Treat "
        "findings as consistent, explainable triage; re-run with the dual AI "
        "panel for judgment-grade scoring.")
    return out


def narrative(packet: dict) -> dict:
    """base.narrative, then drop any Present/Partial citation whose anchor
    fails the R25 concreteness contract — fewer citations is honest;
    an ungrounded one fails validation (observed on prose-heavy SDDs)."""
    out = base.narrative(packet)
    cits = out.get("zms_calibration_citations") or {}
    for dim, entries in cits.items():
        kept = [e for e in entries
                if e.get("verdict") not in ("Present", "Partial")
                or _concrete(e.get("evidence_anchor") or "")]
        cits[dim] = kept or [{
            "zms_criterion_id": f"{dim}A.general",
            "source_label": "Zennify SDD standard",
            "brd_ref": "BRD section 1", "sdd_ref": "SDD body",
            "verdict": "Absent",
            "evidence_anchor": "topic absent from SDD",
            "negative_evidence": {"searched_sections": ["full document"],
                                  "searched_terms": ["dimension", dim]},
            "observation": "No concretely groundable citation for this "
                           "dimension; recorded as negative evidence."}]
    return out


HANDLERS = {"components": base.components, "features": features,
            "pass": scoring_pass, "reconcile": reconcile, "review": review,
            "narrative": narrative, "exec_narrative": exec_narrative,
            "evidence": base.evidence}


def execute(packet: dict) -> dict:
    return HANDLERS[packet["kind"]](packet)


def usage_for(packet: dict) -> dict:
    """TR-8: report the judge SLOT the packet was addressed to; the engine
    field carries the truth of what executed (same convention as --engine
    mock). Zero tokens, zero cost — no model exists in this path."""
    meta = packet.get("meta") or {}
    return {"engine": ENGINE, "judge": meta.get("judge") or "claude-code",
            "model": MODEL, "input_tokens": 0, "output_tokens": 0,
            "total_cost_usd": 0.0}
