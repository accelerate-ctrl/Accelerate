#!/usr/bin/env python3
"""
report_build_sdd_review.py - Section G for Mode B (single-SDD SA review).

Builds the SDD Review Report. It MIRRORS the Mode A Diagnostic Report verbatim -
same branded cover, same section sequence, and the same section labels and card
fields - drawing its chrome and layout helpers from report_build_substantive and
report_style so the two deliverables share ONE structure and ONE styling
vocabulary. It differs from Mode A only where Mode B genuinely has less to say:

  - no methodology lift, no second lane, no blinding, no five-pass variance, and
    no comparative columns (one SDD is reviewed, not two compared);
  - "The judgment" replaces "The verdict"; "Where it's strong" / "Where it falls
    short" replace "Where the methodology paid off" / "Where ZenAgent trailed";
  - the gap-set reading is single-lane (no ZenAgent-specific-vs-shared split);
  - "Grounding" on each card cites criterion . dimension . priority (no
    "vs off-the-shelf").

The seven dimensions and the ZMS criteria are a LENS for structuring findings,
not a scorecard. No scoring, lift, or R1-R25 numeric validation is consumed
(unless the operator opted into scoring, handled as a separate numeric annex).

Usage:
    python3 report_build_sdd_review.py \\
        --bundle <run>/sdd-review-bundle.json \\
        --release <run>/release-awareness-A.json \\
        --output <run>/sdd-review-report.docx [--top-n 8] [--engagement NAME]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contracts
import report_style as _STYLE
# Canonical chrome + layout helpers: single-sourced from the Mode A builder so
# the SDD Review Report is structurally identical to the Diagnostic Report.
from report_build_substantive import (
    section_head, label, body, lead_para, callout, data_table, card,
    DARK, TEAL, BLUE, WHITE, POS, NEG, GRAY, ROW_ALT, F_REG, DIMNAMES, _num)
from docx import Document
from docx.shared import Pt

# Qualitative verdict vocabulary, parallel to Mode A's gate dispositions
# (Accept / Accept-with-changes / Rework / Redo).
VERDICTS = {
    "build_ready": ("Build-ready",
        "Acceptable to build from now; only minor refinements remain."),
    "build_ready_with_conditions": ("Build-ready with conditions",
        "Acceptable once the listed conditions are resolved before or early in build."),
    "needs_targeted_refinement": ("Needs targeted refinement",
        "Rework: close the material gaps below before this is build-ready."),
    "not_ready": ("Not yet build-ready",
        "Redo: the gaps are significant enough that building now carries real delivery risk."),
}
VERDICT_COLOR = {"build_ready": POS, "build_ready_with_conditions": TEAL,
                 "needs_targeted_refinement": NEG, "not_ready": NEG}


def _clip(s, n=60):
    return _STYLE._clip(s, n)


def _join(v):
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v)
    return str(v) if v else ""


def _dim_from_ref(ref):
    for ch in str(ref or ""):
        if ch.isdigit():
            return f"Dimension {ch}"
    return "Dimension -"


def _release_headline(release: dict) -> str:
    if not release:
        return "Release currency was not assessed for this review."
    f = release.get("findings", []) or []
    retired = [x for x in f if x.get("status") == "retired"]
    eos = [x for x in f if x.get("status") == "end_of_support"]
    sup = [x for x in f if x.get("status") == "superseded"]
    if retired:
        names = ", ".join(x.get("mechanism_name", "") for x in retired[:3])
        return (f"Blocking: the design depends on retired Salesforce feature(s) ({names}), "
                "which must be replaced before build (Section 3).")
    parts = []
    if eos:
        parts.append(f"{len(eos)} end-of-support dependency(ies)")
    if sup:
        parts.append(f"{len(sup)} superseded-version item(s)")
    if parts:
        return ("Release currency: " + " and ".join(parts) +
                " to address as technical debt / modernisation (Section 3); no blocking retirements.")
    return "Release currency: clean - no retired, end-of-support, or superseded dependencies detected."


def _release_table(doc, release):
    findings = (release or {}).get("findings", []) or []
    flagged = [f for f in findings if f.get("status") != "in_force"]
    if not findings:
        body(doc, "Release currency was not assessed for this review.", 10, GRAY)
        return
    if not flagged:
        body(doc, "Clean for this lane: the named Salesforce mechanisms were crosswalked live "
                  "against Salesforce-controlled sources, and none is retired, end-of-support, or "
                  "superseded.", 10, DARK)
        return
    rank = {"retired": 0, "end_of_support": 1, "superseded": 2, "in_force_unverified": 3}
    flagged.sort(key=lambda f: rank.get(f.get("status"), 9))
    rows = []
    for f in flagged:
        src = f.get("salesforce_source") or "; ".join((f.get("corroboration") or [])[:1]) or "(unverified)"
        rows.append([f.get("mechanism_name", ""), f.get("status", ""), f.get("confidence", ""),
                     _clip(f.get("recommended_successor", ""), 60), _clip(src, 40)])
    data_table(doc, ["Mechanism", "Status", "Confidence", "Recommended successor", "Source"], rows)


def _agg(fbd, key):
    """Aggregate strengths or gaps across dimensions into a readable sentence."""
    bits = []
    for dim in range(1, 8):
        b = fbd.get(str(dim)) or {}
        items = b.get(key) or []
        if items:
            bits.append(f"{DIMNAMES[dim]} ({items[0]}{'; ...' if len(items) > 1 else ''})")
    return "; ".join(bits)


def _gap_themes(fbd):
    dims = [f"{DIMNAMES[int(d)]} ({len((fbd[d] or {}).get('gaps', []))})"
            for d in sorted(fbd) if (fbd[d] or {}).get("gaps")]
    return "Gaps cluster on: " + ("; ".join(dims) if dims else "no recorded gaps") + "."


def _synth_narrative(bundle, release, origin_disp, fbd, recs):
    judgment = bundle.get("judgment_statement", "") or ""
    rationale = bundle.get("rationale", "") or ""
    strong = _agg(fbd, "strengths")
    short = _agg(fbd, "gaps")
    highs = [r.get("title") or r.get("what") or r.get("what_to_change") or ""
             for r in recs if r.get("priority") == "High"]
    nxt = ("Act first on the High-priority refinements" +
           (": " + "; ".join([h for h in highs[:3] if h]) + "." if any(highs) else
            " under Priority recommendations.")) if recs else \
          "No refinements were required; the design met the calibration lens on every dimension reviewed."
    return {
        "what_we_evaluated": (f"One Solution Design Document ({origin_disp}) was reviewed against the "
                              "applicable ZMS criteria across all seven solution-architecture dimensions, "
                              "using the criteria as a lens for what good looks like rather than as a scorecard."),
        "the_judgment": (judgment + ((" " + rationale) if rationale else "")).strip(),
        "where_strong": (f"The design is strongest on {strong}." if strong else ""),
        "where_short": (f"The design falls short on {short}." if short else ""),
        "release_currency": _release_headline(release),
        "confidence_caveats": ("This is a single-lane qualitative review, so there is no comparative "
                               "baseline, no blinding, and no five-pass variance statistic. The findings "
                               "are a senior-SA reading to verify against the cited evidence, not a "
                               "calibrated measurement."),
        "what_next": nxt,
    }


def build(bundle: dict, release: dict, out_path: str, top_n: int = 8, engagement: str = None) -> None:
    doc = Document()
    doc.styles["Normal"].font.name = F_REG
    doc.styles["Normal"].font.size = Pt(10.5)
    sec = doc.sections[0]
    try:
        _STYLE.add_logo_header(sec); _STYLE.add_footer(sec)
    except Exception:
        pass

    run_id = bundle.get("run_id", "")
    gen = bundle.get("generated_at", "")
    zmsv = bundle.get("zms_version", contracts.FRAMEWORK_VERSION)
    origin = bundle.get("origin_label", "unspecified")
    origin_disp = {"zenagent": "ZenAgent", "off_the_shelf": "Off-the-shelf",
                   "unspecified": "Unspecified"}.get(origin, origin)
    verdict_key = bundle.get("verdict", "needs_targeted_refinement")
    vlabel, vmeaning = VERDICTS.get(verdict_key, VERDICTS["needs_targeted_refinement"])
    eng = engagement or bundle.get("engagement") or "(engagement)"
    fbd = bundle.get("findings_by_dimension", {}) or {}
    recs = bundle.get("recommendations", []) or []

    # ---- canonical branded cover (shared with the Mode A Diagnostic Report) ----
    try:
        _STYLE.cover_banner(
            doc, doc_title="SDD Review Report",
            subtitle_bits=[eng, "SDD Review (Mode B)"],
            grid_pairs=[("Prepared by", "Zennify"), ("Engagement", eng),
                        ("Run ID", run_id), ("Generated", gen),
                        ("Calibration", f"ZMS {zmsv} (frozen)"), ("SDD origin", origin_disp),
                        ("Judgment", vlabel),
                        ("Confidentiality", "Zennify Confidential - distribution restricted")])
    except Exception:
        pass

    # ---- header / run metadata ----
    label(doc, "SDD Review", TEAL)
    data_table(doc, ["RUN ID", "GENERATED", "CALIBRATION", "SDD ORIGIN"],
               [[run_id, gen, f"ZMS {zmsv}", origin_disp]])

    # ---- calibration coverage (advisory) ----  (self-consistency note; Mode B is not scored)
    label(doc, "Calibration coverage (advisory)")
    body(doc, "This is a qualitative SDD review: the design was read against the ZMS calibration as a "
              "lens for what good looks like, not scored. The SDD origin label did not influence any "
              "finding. Treat the findings as a senior-SA opinion to verify against the cited evidence, "
              "not a calibrated measurement.", 9.5, GRAY)

    # ---- EXECUTIVE SUMMARY ----
    label(doc, "Executive summary")
    section_head(doc, "Bottom line")
    judgment = bundle.get("judgment_statement") or vmeaning
    callout(doc, [
        ("BOTTOM LINE UP FRONT", 9.5, BLUE, True),
        (f"Situation.  One Solution Design Document ({origin_disp}) was reviewed against the applicable "
         "ZMS criteria across the seven solution-architecture dimensions, used as a calibration lens "
         "rather than a scorecard.", 10.5, DARK, False),
        (f"Reading.  {judgment}", 10.5, DARK, False),
        (f"Recommendation.  {vlabel} - {vmeaning}", 11, VERDICT_COLOR.get(verdict_key, TEAL), True),
    ])
    # (no Stability line - Mode B has no five-pass variance)

    # ---- executive narrative: model-authored if supplied, else synthesized ----
    narr = bundle.get("exec_narrative") or {}
    syn = _synth_narrative(bundle, release, origin_disp, fbd, recs)
    for key, lbl in (("what_we_evaluated", "What we evaluated"),
                     ("the_judgment", "The judgment"),
                     ("where_strong", "Where it's strong"),
                     ("where_short", "Where it falls short"),
                     ("release_currency", "Release currency"),
                     ("confidence_caveats", "Confidence and caveats"),
                     ("what_next", "What to do next")):
        val = (narr.get(key) or syn.get(key) or "").strip()
        if val:
            lead_para(doc, lbl, val)

    # ---- At a glance: per-dimension lens reading (no scores) ----
    section_head(doc, "At a glance")
    rows = []
    for dim in range(1, 8):
        b = fbd.get(str(dim)) or {}
        s = "; ".join(b.get("strengths", [])[:2]) or "-"
        g = "; ".join(b.get("gaps", [])[:2]) or "-"
        rows.append([f"D{dim} {DIMNAMES[dim]}", _clip(s, 58), _clip(g, 58)])
    data_table(doc, ["Dimension (lens)", "Strengths", "Gaps"], rows)
    body(doc, "Verdict scale:  Build-ready  .  Build-ready with conditions  .  Needs targeted "
              "refinement  .  Not yet build-ready.", 9, GRAY)

    # ---- PRIORITY RECOMMENDATIONS (cards) ----
    label(doc, "Priority recommendations")
    order = {"High": 0, "Medium": 1, "Low": 2}
    recs_sorted = sorted(recs, key=lambda r: order.get(r.get("priority", "Medium"), 1))
    shown = recs_sorted[:top_n]
    overflow = recs_sorted[top_n:]
    if not shown:
        callout(doc, [("No refinement recommendations were generated; the design met the calibration "
                       "lens on every dimension reviewed.", 10.5, DARK, False)], fill=ROW_ALT)
    else:
        body(doc, f"The {len(shown)} highest-priority refinements follow"
                  + (f"; a further {len(overflow)} lower-priority item(s) are listed in Appendix A."
                     if overflow else "."), 10.5, DARK)
        for i, r in enumerate(shown, 1):
            title = r.get("title") or r.get("what") or r.get("what_to_change") or "(untitled)"
            gap = r.get("what") or r.get("what_to_change") or ""
            why = r.get("why") or r.get("why_it_matters") or ""
            how = r.get("good") or r.get("what_good_looks_like") or ""
            done = r.get("done_when") or ""
            where = r.get("where") or _join(r.get("evidence_refs"))
            ref = r.get("lens_ref") or r.get("zms_ref") or _join(r.get("affected_zms_refs"))
            fields = [("The gap.", gap, DARK), ("Why it matters.", why, DARK),
                      ("How to close it.", how, TEAL)]
            if done:
                fields.append(("Done when.", done, DARK))
            if where:
                fields.append(("Where in the SDD.", where, DARK))
            fields.append(("Grounding.",
                           f"{ref} . {_dim_from_ref(ref)} . {r.get('priority','Medium')} priority", BLUE))
            card(doc, f"#{i}  {title}", fields)

    # ---- BODY ----
    # 1. Findings by dimension (prose; analog of Mode A per-dimension reading)
    section_head(doc, "1. Findings by dimension")
    any_f = False
    for dim in range(1, 8):
        b = fbd.get(str(dim)) or {}
        if not (b.get("strengths") or b.get("gaps")):
            continue
        any_f = True
        label(doc, f"Dimension {dim} - {DIMNAMES[dim]}")
        for s in b.get("strengths", []):
            body(doc, f"Strength.  {s}", 10, POS, after=2)
        for g in b.get("gaps", []):
            body(doc, f"Gap.  {g}", 10, NEG, after=2)
    if not any_f:
        body(doc, "No dimension-level findings were recorded for this review.", 10, GRAY)

    # 2. Reading the gap set (single-lane synthesis; analog of Mode A IP-gap reading)
    n_gaps = sum(len((v or {}).get("gaps", [])) for v in fbd.values())
    if n_gaps:
        section_head(doc, "2. Reading the gap set")
        n_dims_gap = len([d for d in fbd if (fbd[d] or {}).get("gaps")])
        card(doc, "Reading the gap set", [
            ("The headline.", f"{n_gaps} gap(s) were identified across {n_dims_gap} dimension(s), read "
             "against the Zennify calibration bar for what good looks like.", DARK),
            ("The themes.", _gap_themes(fbd), DARK),
            ("What to prioritise.", "Close the High-priority refinements first (Priority "
             "recommendations); route recurring, cross-cutting gaps to the methodology lead as "
             "candidate ZMS criteria rather than one-off fixes.", TEAL),
        ])

    # 3. Release currency (Mode A body section 4)
    section_head(doc, "3. Release currency")
    _release_table(doc, release)

    # ---- APPENDICES ----
    doc.add_page_break()
    label(doc, "Appendix . Supporting evidence")

    section_head(doc, "Appendix A. Prioritised SA review list")
    if recs_sorted:
        rows = [[str(i), _clip(r.get("title") or r.get("what") or r.get("what_to_change") or "", 56),
                 r.get("priority", "Medium"),
                 _clip(r.get("lens_ref") or r.get("zms_ref") or _join(r.get("affected_zms_refs")), 28)]
                for i, r in enumerate(recs_sorted, 1)]
        data_table(doc, ["#", "Refinement", "Priority", "Lens"], rows)
    else:
        body(doc, "No refinements; nothing to prioritise.", 10, GRAY)

    section_head(doc, "Appendix B. Run provenance")
    prov = [["Framework version", contracts.FRAMEWORK_VERSION],
            ["Mode", "B - SDD Review (single lane, qualitative)"],
            ["Run ID", run_id], ["Generated", gen],
            ["Calibration", f"ZMS {zmsv} (frozen)"],
            ["SDD origin", f"{origin_disp} (label only; did not influence findings)"],
            ["Scoring", "enabled (numeric annex produced separately)"
             if bundle.get("scoring_enabled") else "not performed (qualitative review by design)"],
            ["Release currency", "live path used"
             if (release or {}).get("live_path_used") else "register-based / not run this session"]]
    data_table(doc, ["Field", "Value"], prov)

    section_head(doc, "Appendix C. ZMS coverage matrix")
    cov_rows = []
    for dim in range(1, 8):
        b = fbd.get(str(dim)) or {}
        status = "reviewed" if (b.get("strengths") or b.get("gaps")) else "no findings"
        cov_rows.append([f"D{dim}", DIMNAMES[dim], str(len(b.get("strengths", []))),
                         str(len(b.get("gaps", []))), status])
    data_table(doc, ["#", "Dimension (lens)", "Strengths", "Gaps", "Status"], cov_rows)
    body(doc, "Critical-floor criteria (story coverage, record/sharing access, external-user exposure, "
              "data model, capability decomposition, security and sharing model) are treated as "
              "build-blocking when absent, consistent with the frozen ZMS standard.", 9, GRAY)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_path)
    try:
        _STYLE._patch_zoom(out_path)
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser(description="Mode B SDD Review Report builder (mirrors Mode A structure)")
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--release", required=False, help="release-awareness JSON from release_crosswalk")
    ap.add_argument("--output", required=True)
    ap.add_argument("--top-n", type=int, default=8)
    ap.add_argument("--engagement", default=None)
    args = ap.parse_args()

    bundle = json.loads(Path(args.bundle).read_text(encoding="utf-8"))
    release = {}
    if args.release and Path(args.release).exists():
        release = json.loads(Path(args.release).read_text(encoding="utf-8"))
    build(bundle, release, args.output, top_n=args.top_n, engagement=args.engagement)
    print(json.dumps({"status": "ok", "mode": "sdd_review", "report_path": args.output,
                      "recommendations_total": len(bundle.get("recommendations", [])),
                      "top_n": args.top_n}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
