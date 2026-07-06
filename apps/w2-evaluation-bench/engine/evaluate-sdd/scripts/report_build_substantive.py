#!/usr/bin/env python3
"""
report_build_substantive.py - build the Mode A Diagnostic Report in the substantive,
decision-led format defined by the approved standard (diagnostic-report_10.docx).

What makes this report substantive (vs the older concise builder):
  - Priority recommendation CARDS with five grounded fields each (The gap / Why it
    matters / How to close it / Done when / Where in the SDD), sourced from the
    recommended_actions + ZMS depth bar, not one-line bullets.
  - A per-dimension VALUE table where the ZA-vs-OTS difference is visible, and where
    a dimension on which OFF-THE-SHELF BEAT ZENAGENT is called out explicitly with an
    OTS-AHEAD flag, including where and why.
  - In-house IP gap entries each carrying an Evidence anchor + ZMS depth bar.
  - The substance lives in the BODY; the appendix holds only the SA review list.
  - Four-band quality model (rubric s.3) carrying the disposition, read overall and per dimension, as the headline.

Reuses diagnostic_report_populate.build_diag_tokens for validated data extraction.
"""
import sys, os, json, argparse
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import diagnostic_report_populate as D
try:
    from score_sheet_populate import (band_for_pct, band_for_dim, gate_for_pct,
                                       DIM_MAX, BAND_MEANING, GATE_DISPOSITION)
except Exception:
    # Standalone fallback. CRITICAL: this must NOT hold a second copy of the
    # band/gate/disposition VALUES — duplicated tables drift and were the root
    # cause of the live "Redo on a passing score" defect. Everything here is
    # derived from contracts.py, the single source of truth (rubric sections 3 & 8).
    import contracts as _c
    DIM_MAX = {d: (_c.dim_max(d, False), _c.dim_max(d, True)) for d in range(1, 8)}
    def band_for_pct(p):
        return _c.band_for_pct(p) if p is not None else ""
    def gate_for_pct(p, vf=False):
        return _c.gate_for_pct(p, vf) if p is not None else ""
    def band_for_dim(mean, dim, ih):
        mx = _c.dim_max(dim, ih)
        return band_for_pct(100.0 * mean / mx) if (mean is not None and mx) else ""
    # Disposition text and band meanings come straight from contracts; no copies.
    BAND_MEANING = {b: _c.BAND_DISPOSITION[b][1] for b in _c.BAND_LABELS}
    GATE_DISPOSITION = dict(_c.GATE_DISPOSITION)

# ---------- brand ----------
# Single source of brand truth: report_style.py (shared with the Mode B builder).
# The local names below are ALIASES of the imported tokens, not copies — this
# eliminates the palette-drift risk while keeping the existing layout code, which
# references DARK/TEAL/etc., unchanged. If report_style is somehow unavailable,
# fall back to the literal brand hex values so the report still builds on-brand.
try:
    import report_style as _STYLE
    DARK = _STYLE.DARK_TEAL; TEAL = _STYLE.BRAND_TEAL
    BLUE = _STYLE.MUTED_BLUE; WHITE = _STYLE.WHITE
    POS = _STYLE.POS; NEG = _STYLE.NEG; GRAY = _STYLE.GRAY
    HDR_FILL = _STYLE.HDR_FILL; ROW_ALT = _STYLE.ROW_EVEN; BLUF_FILL = _STYLE.BLUF_FILL
    CARD_FILL = "f2f6fb"
    F_REG = _STYLE.F_REG; F_SEMI = _STYLE.F_SEMI
    _HAVE_STYLE = True
except Exception:
    _STYLE = None
    DARK = RGBColor(0x1c, 0x4a, 0x4d); TEAL = RGBColor(0x13, 0x9f, 0x94)
    BLUE = RGBColor(0x80, 0x94, 0xc0); WHITE = RGBColor(0xff, 0xff, 0xff)
    POS = RGBColor(0x05, 0x96, 0x69); NEG = RGBColor(0xc2, 0x50, 0x08); GRAY = RGBColor(0x66, 0x66, 0x66)
    HDR_FILL = "139f94"; ROW_ALT = "e8f7f6"; BLUF_FILL = "e8f7f6"; CARD_FILL = "f2f6fb"
    F_REG = "DM Sans"; F_SEMI = "DM Sans SemiBold"
    _HAVE_STYLE = False
BAND_COLOR = {"STRONG": POS, "GOOD": TEAL, "ADEQUATE": NEG, "WEAK": NEG}

DIMNAMES = {1: "BRD Comprehension", 2: "Requirement Coverage", 3: "Salesforce Solution Fit",
            4: "Design Specificity", 5: "Dependencies and Assumptions", 6: "Scope Discipline",
            7: "Estimation Readiness"}


def _run(p, text, size=10.5, color=DARK, bold=False, font=None):
    r = p.add_run(text); r.font.size = Pt(size); r.font.bold = bold
    r.font.color.rgb = color; r.font.name = font or F_REG
    return r


def _shade(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr(); shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear"); shd.set(qn("w:fill"), fill); tcPr.append(shd)


def section_head(doc, text):
    p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(14); p.paragraph_format.space_after = Pt(4)
    _run(p, text, 20, TEAL, font=F_SEMI)
    return p


def label(doc, text, color=BLUE):
    p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(2)
    _run(p, text.upper(), 9.5, color, bold=True)


def body(doc, text, size=10.5, color=DARK, after=6):
    p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(after); p.paragraph_format.line_spacing = 1.12
    _run(p, text, size, color)
    return p


def lead_para(doc, label_text, body_text, size=10.5, after=6):
    """A narrative paragraph with a bold lead-in label, matching the target
    Diagnostic Report's executive-summary style: 'Label.  body text...'. Used to
    render the model-authored exec-summary narrative when supplied."""
    p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(after); p.paragraph_format.line_spacing = 1.18
    _run(p, f"{label_text}.  ", size, DARK, bold=True)
    _run(p, body_text, size, DARK)
    return p


def callout(doc, lines, fill=BLUF_FILL):
    t = doc.add_table(rows=1, cols=1); t.alignment = WD_TABLE_ALIGNMENT.CENTER
    c = t.rows[0].cells[0]; _shade(c, fill)
    c.paragraphs[0].text = ""
    for i, (txt, sz, col, bd) in enumerate(lines):
        p = c.paragraphs[0] if i == 0 else c.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        _run(p, txt, sz, col, bold=bd)
    return t


def data_table(doc, headers, rows, widths=None, flag_col=None):
    t = doc.add_table(rows=1, cols=len(headers)); t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.LEFT
    for i, h in enumerate(headers):
        c = t.rows[0].cells[i]; _shade(c, HDR_FILL); c.paragraphs[0].text = ""
        _run(c.paragraphs[0], h, 9.5, WHITE, bold=True)
    for ri, row in enumerate(rows):
        cells = t.add_row().cells
        for ci, val in enumerate(row):
            c = cells[ci]; c.paragraphs[0].text = ""
            txt = str(val)
            color = DARK
            if flag_col is not None and ci == flag_col:
                if "OTS-AHEAD" in txt or "UNDERPERF" in txt:
                    color = NEG
                elif txt.startswith("+"):
                    color = POS
            _run(c.paragraphs[0], txt, 9.5, color, bold=(flag_col is not None and ci == flag_col and txt not in ("", "n/a")))
            if ri % 2 == 1:
                _shade(c, ROW_ALT)
    if widths:
        from docx.shared import Inches
        for row in t.rows:
            for ci, w in enumerate(widths):
                row.cells[ci].width = Inches(w)
    return t


def card(doc, title_line, fields, fill=CARD_FILL):
    """A recommendation/gap card: a shaded header cell + the grounded fields beneath."""
    t = doc.add_table(rows=1, cols=1); t.alignment = WD_TABLE_ALIGNMENT.CENTER
    c = t.rows[0].cells[0]; _shade(c, fill); c.paragraphs[0].text = ""
    _run(c.paragraphs[0], title_line, 10.5, DARK, bold=True)
    for k, v, col in fields:
        p = c.add_paragraph(); p.paragraph_format.space_after = Pt(1)
        _run(p, k + "  ", 9.5, col, bold=True)
        _run(p, v, 9.5, DARK)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--za-bundle", required=True)
    ap.add_argument("--ots-bundle", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--top-n", type=int, default=5)
    ap.add_argument("--accuracy-gate", default=None,
                    help="accuracy-gate.json from batch 2.5; renders the calibration "
                         "transparency block. If the check blocked, the report carries a "
                         "prominent VERDICT SELF-CONSISTENCY CHECK FAILED banner.")
    args = ap.parse_args()

    bundle = json.load(open(args.bundle))
    za = json.load(open(args.za_bundle))
    ots = json.load(open(args.ots_bundle))
    t, review_lists, lists = D.build_diag_tokens(bundle, za, ots)

    # ---- v4.7 dual-judge context (None/False on frozen five-pass runs) ----
    import contracts as _contracts
    _s1 = bundle.get("section_1") or {}
    dual = bool(_s1.get("judge_lifts")) or _s1.get("protocol") == "dual-judge"
    _JA, _JB = _contracts.JUDGES

    def _dissent_dims(b):
        dims = set()
        for dd in (b.get("dissents") or []):
            cid = dd.get("criterion_id") or ""
            sk = dd.get("sub_key") or ""
            if cid:
                dims.add(int(cid[0]))
            elif sk.startswith("sub:"):
                dims.add(int(sk.split(":")[1]))
        return dims

    dis_dims_za = _dissent_dims(za) if dual else set()
    dis_dims_ots = _dissent_dims(ots) if dual else set()
    agg_za = (za.get("agreement_stats") or {}) if dual else {}
    agg_ots = (ots.get("agreement_stats") or {}) if dual else {}

    # Guardrail 3: fail-loud on cross-script handoffs. Centralized integrity
    # checks so a hollow report is never produced silently (catches the QA-02/04
    # class: scoring bundles present but missing content_coding, etc.).
    import pipeline_integrity as PI
    handoff_warnings = PI.check_scoring_bundle_for_report(za, ots)
    _cov = lists.get("zms_coverage_matrix", []) or []
    _has_coding = bool((za or {}).get("content_coding") or (ots or {}).get("content_coding"))
    if not _cov and _has_coding:
        handoff_warnings.append(
            "[report] WARNING: coverage matrix is empty but the scoring bundles "
            "contain content_coding; the matrix, IP-gap analysis, and 'why' cards "
            "will be empty (QA-02/QA-03).")
    for w in handoff_warnings:
        sys.stderr.write(w + "\n")

    doc = Document()
    # base style
    doc.styles["Normal"].font.name = F_REG; doc.styles["Normal"].font.size = Pt(10.5)

    # Zennify brand chrome (logo header + paginated footer), single-sourced from
    # report_style so the comparative report carries the same branding as the
    # Mode B SDD-review report. Degrades to a text wordmark if the logo asset is
    # not present in this environment.
    if _HAVE_STYLE:
        try:
            sec = doc.sections[0]
            _STYLE.add_logo_header(sec)
            _STYLE.add_footer(sec)
        except Exception:
            pass

    # ---- canonical branded cover (shared with the Mode B SDD Review Report) ----
    if _HAVE_STYLE:
        try:
            _eng = t.get("engagement") or bundle.get("engagement") or "(engagement)"
            _za = _num(t.get("za_total"))
            _wn = str(t.get("lift_within_noise", "")).lower() == "true"
            _hl = (f"ZenAgent {fmt(_za)}/100 {band_for_pct(_za)}  .  "
                   + ("no measurable methodology lift vs off-the-shelf (within pass noise)"
                      if _wn else
                      f"methodology lift {t.get('methodology_lift','')} vs off-the-shelf"))
            _STYLE.cover_banner(
                doc, doc_title="Diagnostic Report",
                subtitle_bits=[_eng, "Comparative (Mode A)"],
                grid_pairs=[("Prepared by", "Zennify"), ("Engagement", _eng),
                            ("Run ID", t.get("run_id", "")), ("Generated", t.get("run_timestamp", "")),
                            ("Calibration", f"ZMS {t.get('zms_version','')} (frozen)"),
                            ("Evaluator model", t.get("model_version", "")),
                            ("Headline result", _hl),
                            ("Confidentiality", "Zennify Confidential - distribution restricted")])
        except Exception:
            pass

    # ---- header / run metadata ----
    label(doc, "Diagnostic Report", TEAL)
    meta = data_table(doc, ["RUN ID", "GENERATED", "CALIBRATION", "EVALUATOR MODEL"],
                      [[t.get("run_id", ""), t.get("run_timestamp", ""),
                        f"ZMS {t.get('zms_version','')}", t.get("model_version", "")]])

    # ---- calibration transparency (verdict self-consistency check) ----
    # Every report states the verdict-step self-consistency basis (or its absence).
    # This is the honesty guardrail: the check measures agreement between the
    # model's verdicts and the deterministic construction-rule labels on a small
    # validation set — it is NOT an external accuracy measurement over all
    # criteria, and the report must never present it as one.
    gate = None
    if args.accuracy_gate:
        try:
            gate = json.load(open(args.accuracy_gate)).get("gate", {})
        except Exception:
            gate = None
    if gate:
        status = gate.get("status", "")
        caveat = gate.get("report_caveat", "")
        if gate.get("blocking"):
            label(doc, "VERDICT SELF-CONSISTENCY CHECK FAILED", RGBColor(0xb0, 0x1c, 0x1c))
            body(doc, caveat, 10.5, RGBColor(0xb0, 0x1c, 0x1c))
        elif status == "advisory":
            label(doc, "Calibration coverage (advisory)")
            body(doc, caveat, 9.5, GRAY)
        else:
            label(doc, "Calibration coverage")
            body(doc, caveat, 9.5, GRAY)
    else:
        # No self-consistency result supplied — say so rather than implying calibration.
        label(doc, "Calibration coverage (advisory)")
        body(doc, "No verdict self-consistency result was supplied for this run, so the "
                  "verdict step's self-consistency was not measured here. Treat the findings "
                  "as a senior-SA opinion to verify against the cited evidence, not a "
                  "calibrated measurement.", 9.5, GRAY)

    # ---- data-integrity banner (Guardrail 3) ----
    # If any handoff check warned, the report says so prominently rather than
    # presenting a possibly-hollow body as if it were complete.
    if handoff_warnings:
        label(doc, "Data-integrity warnings", RGBColor(0xb0, 0x1c, 0x1c))
        body(doc, "This run hit one or more pipeline-integrity warnings; sections "
                  "below may be incomplete. Resolve these and re-run before relying "
                  "on the report:", 9.5, RGBColor(0xb0, 0x1c, 0x1c))
        for w in handoff_warnings:
            body(doc, "- " + w, 9.0, GRAY)

    # ---- EXECUTIVE SUMMARY ----
    label(doc, "Executive summary")
    # quality band + gate verdict for ZA (separate axes, v4.1)
    za_total = _num(t.get("za_total"))
    ots_total = _num(t.get("ots_total"))
    lift = t.get("methodology_lift", "")
    za_band = band_for_pct(za_total); ots_band = band_for_pct(ots_total)
    # Disposition is GATE-driven (rubric section 8), never band-driven (v4.1).
    # Prefer the authoritative per-dimension gate roll-up; fall back to the total.
    za_gate = t.get("za_gate_overall") or gate_for_pct(za_total)
    ots_gate = t.get("ots_gate_overall") or gate_for_pct(ots_total)
    disp, disp_meaning = GATE_DISPOSITION.get(za_gate, ("", ""))

    section_head(doc, "Bottom line")
    # Guardrail 2 — surface the lift's uncertainty HONESTLY. The band is now
    # CORRELATION-ADJUSTED (widened by the ICC design effect), so it is no longer
    # a naive lower bound from assuming independent passes. It still excludes model
    # bias + cross-session variance. Never call it "robust".
    ci_lo = t.get("lift_pass_noise_low", "") or t.get("lift_ci95_low", "")
    ci_hi = t.get("lift_pass_noise_high", "") or t.get("lift_ci95_high", "")
    p_gt0 = t.get("lift_p_gt_0", ""); within_noise = t.get("lift_within_noise", "")
    rho = t.get("pass_correlation_rho", ""); neff = t.get("pass_correlation_neff", "")
    corr_txt = ""
    if rho != "" and neff != "":
        corr_txt = (f" Pass correlation ICC ρ̂={rho} implies {neff} effective passes "
                    f"(of five); the band above is widened by that design effect.")
    if dual:
        # v4.7: uncertainty IS the inter-judge spread (TR-19, Backend §9). The
        # per-lane reliability labels come from the bundles' own agreement
        # stats (computed once in the consensus engine — TR-21; no threshold
        # copies here).
        _jl = _s1.get("judge_lifts") or {}
        _band = _s1.get("lift_band") or [None, None]
        _ao = _s1.get("agreement_overall")
        _sign_holds = (isinstance(_band[0], (int, float)) and isinstance(_band[1], (int, float))
                       and (_band[0] > 0 or _band[1] < 0))
        unc_txt = (f" Per-judge lifts: Claude {fmt(_jl.get(_JA))} / Gemini {fmt(_jl.get(_JB))}; "
                   f"inter-judge band [{fmt(_band[0])}, {fmt(_band[1])}] spans the two judges' "
                   "fully independent reads"
                   + (" — the sign holds across both model families, so the lift is "
                      "directionally robust." if _sign_holds else
                      " — the band crosses zero, so the two model families do not agree on "
                      "the lift's direction; treat it as contested and read the annex.")
                   + (f" Cross-model agreement {_ao}"
                      f" (ZenAgent lane: {agg_za.get('reliability_label', 'n/a')}; "
                      f"off-the-shelf lane: {agg_ots.get('reliability_label', 'n/a')})."
                      if _ao is not None else "")
                   + " The band excludes errors shared by both models and cross-session "
                     "variance; prefer band-level over point comparisons.")
    elif ci_lo != "" and ci_hi != "":
        unc_txt = (f" Correlation-adjusted pass-noise band [{ci_lo}, {ci_hi}] over the five passes, "
                   f"P(lift>0) = {p_gt0}"
                   + (". This band spans zero, so the lift is within scoring noise and is "
                      "directional only." if str(within_noise) == "true"
                      else ". This band excludes zero, so the lift direction holds under "
                           "pass noise.")
                   + corr_txt
                   + " The band still excludes model bias and cross-session variance; "
                     "prefer band-level over point comparisons.")
    else:
        unc_txt = ""
    callout(doc, [
        ("BOTTOM LINE UP FRONT", 9.5, BLUE, True),
        (f"Situation.  Two Solution Design Documents (ZenAgent and off-the-shelf), built from the "
         f"same requirements, were scored independently and blinded against the applicable ZMS criteria.", 10.5, DARK, False),
        (f"Reading.  ZenAgent scores {fmt(za_total)}/100 (quality band {za_band}, gate {za_gate or 'n/a'}); "
         f"off-the-shelf scores {fmt(ots_total)}/100 (quality band {ots_band}, gate {ots_gate or 'n/a'}); "
         f"methodology lift is {lift} points.{unc_txt}", 10.5, DARK, False),
        (f"Recommendation.  {disp or za_band} - {disp_meaning or BAND_MEANING.get(za_band, '')}",
         11, BAND_COLOR.get(za_band, TEAL), True),
    ])
    stab = t.get("za_stability_statement", "")
    if stab:
        body(doc, f"Stability.  {stab}", 9.5, BLUE)

    # ---- Model-authored executive narrative (the depth the target report shows) ----
    # The model writes these grounded paragraphs (naming the actual dimensions,
    # mechanisms, and numbers for THIS engagement) and passes them in the diag
    # bundle under exec_narrative. The builder renders them as labeled lead-in
    # paragraphs. When a paragraph is absent the builder OMITS it rather than
    # inventing filler — but the orchestrator is instructed (SKILL.md / system
    # prompt) to populate the full set so the report reads like the target.
    narr = bundle.get("exec_narrative") or t.get("exec_narrative") or {}
    if isinstance(narr, dict) and narr:
        # canonical order + labels, matching the target Diagnostic Report
        for key, lbl in (
            ("what_we_evaluated", "What we evaluated"),
            ("the_verdict", "The verdict"),
            ("where_paid_off", "Where the methodology paid off"),
            ("where_trailed", "Where ZenAgent trailed or tied"),
            ("release_currency", "Release currency"),
            ("confidence_caveats", "Confidence and caveats"),
            ("what_next", "What to do next"),
        ):
            val = (narr.get(key) or "").strip()
            if val:
                lead_para(doc, lbl, val)

    section_head(doc, "At a glance")
    _lift_cell = (f"{lift} (within noise)" if str(within_noise).lower() == "true" else lift)
    _glance_rows = [["Total score (of 100)", fmt(za_total), fmt(ots_total), _lift_cell],
                    ["Quality band (rubric section 3)", za_band, ots_band, ""],
                    ["Qualification gate (rubric s.8, four-band)", za_gate or "n/a", ots_gate or "n/a", ""],
                    ["Disposition", disp, GATE_DISPOSITION.get(ots_gate, ("", ""))[0], ""],
                    ["Estimation handoff", t.get("za_handoff_status", t.get("handoff_status", "")),
                     t.get("ots_handoff_status", ""), ""]]
    if dual:
        _jl = _s1.get("judge_lifts") or {}
        _band = _s1.get("lift_band") or [None, None]
        _glance_rows.append(["Per-judge lift (Claude / Gemini)", "", "",
                             f"{fmt(_jl.get(_JA))} / {fmt(_jl.get(_JB))}  band [{fmt(_band[0])}, {fmt(_band[1])}]"])
        _glance_rows.append(["Cross-model agreement (per lane)",
                             f"{fmt(agg_za.get('agreement_overall'))} · {agg_za.get('reliability_label', '')}",
                             f"{fmt(agg_ots.get('agreement_overall'))} · {agg_ots.get('reliability_label', '')}",
                             ""])
        _glance_rows.append(["Dissents preserved (see annex)",
                             str(agg_za.get("dissent_count", len(za.get("dissents") or []))),
                             str(agg_ots.get("dissent_count", len(ots.get("dissents") or []))), ""])
    data_table(doc, ["Measure", "ZenAgent", "Off-the-shelf", "Lift"], _glance_rows)
    body(doc, "Four-band quality model (rubric section 3), read on the overall total and per dimension; "
              "each band carries its disposition: STRONG >=80 (Accept) | GOOD 70-79 (Accept with changes) | "
              "ADEQUATE 65-69 (Rework) | WEAK <65 (Redo).", 9.5, BLUE)

    # ---- PRIORITY RECOMMENDATIONS (cards) ----
    section_head(doc, "Priority recommendations")
    actions = lists.get("recommended_actions", []) or bundle.get("recommended_actions", []) or []
    # If the model did not populate explicit recommended_actions, DERIVE them from
    # the in-house IP gaps (highest severity first) so the report never claims "no
    # gaps" while section 5 lists several. Each derived action is grounded in the
    # real criterion, its verdict, and the ZMS depth bar.
    derived = False
    if not actions:
        ipg = lists.get("in_house_ip_gaps", []) or []
        sev_rank = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "": 4}
        ipg_sorted = sorted(ipg, key=lambda r: sev_rank.get(r.get("severity", ""), 4))
        for r in ipg_sorted:
            actions.append({
                "id": r.get("zms_criterion_id", r.get("criterion_id", "")),
                "category": "In-house IP gap",
                "dimension": r.get("dimension", ""),
                "za_verdict": r.get("za_verdict", ""),
                "severity": r.get("severity", ""),
                "diagnosis": (f"ZenAgent scored {r.get('za_verdict','')} on {r.get('zms_criterion_id','')} "
                              f"(a Zennify-source criterion). {('Evidence: ' + r.get('za_anchor')) if r.get('za_anchor') else ''}").strip(),
                "required_content": r.get("depth_bar") or r.get("depth_indicator") or "",
                "why": (f"This is a {r.get('severity','').lower() or 'material'} in-house IP gap: a Zennify "
                        f"differentiator the ZenAgent template did not fully deliver, so it is a direct "
                        f"candidate for template expansion."),
            })
        derived = bool(actions)
    body(doc, f"The {min(args.top_n, len(actions)) if actions else 'top'} highest-impact gaps for the ZenAgent "
              f"methodology, each grounded in the ZMS calibration bar and the dimension's score impact"
              + (" (derived from the in-house IP-gap analysis in section 5)." if derived else "."))
    if not actions:
        body(doc, "No in-house IP gaps and no priority methodology gaps were surfaced for this run: "
                  "ZenAgent met every applicable Zennify-source criterion at depth.", color=GRAY)
    for i, a in enumerate(actions[:args.top_n], 1):
        cid = a.get("id", a.get("zms_criterion_id", f"#{i}"))
        cat = a.get("category", "Framework gap")
        dimn = a.get("dimension", a.get("dim", ""))
        verdict = a.get("za_verdict", a.get("verdict", "Absent"))
        title = f"#{i}  {cid}      {cat}  .  Dimension {dimn}  .  ZenAgent {verdict}"
        gap = a.get("diagnosis") or a.get("gap") or "ZenAgent does not meet this criterion at mechanism level."
        bar = a.get("required_content") or a.get("depth_indicator") or ""
        why = a.get("why") or a.get("evidence") or f"Closing this lifts Dimension {dimn} toward the next band."
        how = a.get("how_to_close") or (f"Specify the required components in the ZenAgent SDD template: {bar}" if bar else
                                        "Add the named components to the relevant SDD module.")
        done = a.get("done_when") or f"the {cid} section re-scores with every required component present and evidence-anchored."
        where = a.get("where") or a.get("contrast") or f"The component module for {cid} in the ZenAgent SDD."
        card(doc, title, [
            ("The gap.", gap, DARK),
            ("Why it matters.", why, DARK),
            ("How to close it.", how, TEAL),
            ("Done when.", done, DARK),
            ("Where in the SDD.", where, DARK),
        ])

    # ---- 1. Headline lift ----
    section_head(doc, f"1. ZenAgent {lift_phrase(lift, within_noise, neff)}")
    body(doc, f"Methodology lift is {lift} points: ZenAgent {fmt(za_total)}/100 against "
              f"off-the-shelf {fmt(ots_total)}/100. The lift is the sum of the per-dimension "
              f"differences in section 3.")

    # ---- 1.1 Estimation handoff status ----
    s11 = bundle.get("section_1_1") or {}
    if s11:
        section_head(doc, "1.1 Estimation handoff status")
        body(doc, "Whether each lane is ready to hand off to estimation, and the basis for that "
                  "determination (a lane is Ready only when every gated dimension clears its "
                  "qualification threshold).", 9.5, GRAY)
        data_table(doc, ["Lane", "Status", "Derivation basis"],
                   [["ZenAgent", s11.get("za_status", ""), s11.get("za_basis", "")],
                    ["Off-the-shelf", s11.get("ots_status", ""), s11.get("ots_basis", "")]],
                   widths=[1.3, 1.4, 4.0])

    # ---- 2. Per-dimension bands against the 80% gate ----
    section_head(doc, "2. Both lanes measured against the 80% qualification threshold per dimension")
    body(doc, "Each dimension is banded on its score as a percentage of the dimension maximum "
              "(rubric s.3, four-band: STRONG >=80 | GOOD 70-79 | ADEQUATE 65-69 | WEAK <65), and "
              "measured against the 80% qualification gate. This shows where each design clears or "
              "fails the bar dimension by dimension; the overall band is the headline verdict.")
    ih = str(t.get("integration_heavy", "")).lower() == "true"
    band_rows = []
    for d in range(1, 8):
        base, ihm = DIM_MAX[d]; mx = ihm if ih else base
        gate_pts = round(0.80 * mx, 1)
        za_m = _num(t.get(f"za_dim_{d}", t.get(f"za_{d}")))
        ots_m = _num(t.get(f"ots_dim_{d}", t.get(f"ots_{d}")))
        zab = band_for_dim(za_m, d, ih) if za_m is not None else ""
        otsb = band_for_dim(ots_m, d, ih) if ots_m is not None else ""
        za_gate = ("clears" if (za_m is not None and za_m >= gate_pts) else "below") if za_m is not None else ""
        ots_gate = ("clears" if (ots_m is not None and ots_m >= gate_pts) else "below") if ots_m is not None else ""
        band_rows.append([f"D{d}", DIMNAMES[d], str(mx), str(gate_pts),
                          fmt(za_m), za_gate, fmt(ots_m), ots_gate])
    data_table(doc, ["Dim", "Dimension", "Max", "80% gate", "ZA", "ZA gate", "OTS", "OTS gate"],
               band_rows, widths=[0.45, 1.7, 0.45, 0.7, 0.6, 0.85, 0.6, 0.85])

    # ---- 3. Where the methodology added value (and where OTS won) ----
    section_head(doc, "3. Where the methodology added value, dimension by dimension")
    body(doc, "Per-dimension lift (ZA minus OTS). A negative lift means the off-the-shelf design "
              "scored higher on that dimension; those rows are flagged OTS-AHEAD and explained below.")
    lift_rows = []
    ots_ahead = []
    for d in range(1, 8):
        za_m = _num(t.get(f"za_{d}", t.get(f"za_dim_{d}")))
        ots_m = _num(t.get(f"ots_{d}", t.get(f"ots_dim_{d}")))
        if za_m is None or ots_m is None:
            diff = None; flag = ""
        else:
            diff = round(za_m - ots_m, 1)
            if diff < 0:
                flag = "OTS-AHEAD"; ots_ahead.append((d, za_m, ots_m, diff))
            elif t.get(f"flag_{d}") == "UNDERPERFORMANCE":
                flag = "UNDERPERFORMANCE"
            else:
                flag = "n/a"
        # v4.7: a recorded cross-judge dissent on this dimension is flagged in
        # the value table too — the score stands (conservative consensus) but
        # the reader is pointed at the annex (judge provenance, FR-6/SM-4).
        if dual and d in (dis_dims_za | dis_dims_ots):
            flag = "DISSENT" if flag in ("n/a", "") else f"{flag} +DISSENT"
        lift_rows.append([f"D{d}", DIMNAMES[d], fmt(za_m), fmt(ots_m),
                          ("+%.1f" % diff if isinstance(diff, float) and diff >= 0 else fmt(diff)), flag])
    lift_rows.append(["", "Total", fmt(za_total), fmt(ots_total), lift, ""])
    data_table(doc, ["Dim", "Dimension", "ZA", "OTS", "Lift (ZA - OTS)", "Flag"], lift_rows,
               widths=[0.5, 2.0, 0.7, 0.7, 1.3, 1.4], flag_col=5)

    # Dynamic finding line: name the dimensions that actually drove the lift this
    # run, so the section reports THIS evaluation rather than a generic definition.
    drivers = []
    for d in range(1, 8):
        za_m = _num(t.get(f"za_{d}", t.get(f"za_dim_{d}")))
        ots_m = _num(t.get(f"ots_{d}", t.get(f"ots_dim_{d}")))
        if za_m is not None and ots_m is not None:
            drivers.append((round(za_m - ots_m, 1), d))
    pos = sorted([x for x in drivers if x[0] > 0], reverse=True)[:3]
    if pos:
        named = ", ".join(f"D{d} {DIMNAMES[d]} (+{diff:.1f})" for diff, d in pos)
        body(doc, f"In this run the lift was driven most by {named}"
                  + (f"; {len(ots_ahead)} dimension(s) where off-the-shelf led are flagged below."
                     if ots_ahead else "; ZenAgent led or tied on every dimension."), 9.5, GRAY)

    # explicit where-and-why for any dimension OTS won
    if ots_ahead:
        body(doc, "Where off-the-shelf outperformed ZenAgent:", 10.5, NEG, after=2)
        for d, za_m, ots_m, diff in ots_ahead:
            why = ots_win_reason(bundle, lists, d)
            card(doc, f"D{d} {DIMNAMES[d]}: off-the-shelf ahead by {abs(diff):.1f} "
                      f"(OTS {fmt(ots_m)} vs ZA {fmt(za_m)})",
                 [("Where.", f"Dimension {d}, {DIMNAMES[d]}.", NEG),
                  ("Why off-the-shelf scored higher.", why, DARK),
                  ("Action.", "Treat as a methodology regression: the ZenAgent template should "
                              "absorb what the off-the-shelf design did better here.", TEAL)],
                 fill="fbf0ec")
    else:
        body(doc, "ZenAgent met or exceeded the off-the-shelf baseline on every dimension; no "
                  "off-the-shelf-ahead regressions were found in this run.", color=GRAY)

    # ---- 4. Release crosswalk per lane ----
    section_head(doc, "4. Salesforce mechanisms named in each SDD, crosswalked for release currency")
    body(doc, "Every Salesforce mechanism named in each SDD was checked against current Salesforce "
              "sources. Non-current items carry a deduction on Dimension 3 and are listed per lane.")
    for lane_key, lane_name in (("za", "ZenAgent"), ("ots", "Off-the-shelf")):
        all_findings = lists.get(f"release_currency_{lane_key}", []) or []
        # Only non-current mechanisms (retired / end_of_support / superseded) are
        # listed: they carry the Dim-3 deduction. Current and unverified
        # mechanisms are summarized in a single line so no information is lost.
        def _noncurrent(f):
            if "is_noncurrent" in f:
                return bool(f["is_noncurrent"])
            return f.get("status", "") in ("retired", "end_of_support", "superseded")
        findings = [f for f in all_findings if _noncurrent(f)]
        other_count = len(all_findings) - len(findings)
        body(doc, lane_name, 11, DARK, after=2)
        if findings:
            rows = [[f.get("mechanism", ""), f.get("status", ""), f.get("severity", ""),
                     (f.get("source", "") or "")[:38], (f.get("note", f.get("what_to_do", "")) or "")[:60]]
                    for f in findings]
            data_table(doc, ["Mechanism", "Status", "Sev", "Source", "What to do / note"], rows,
                       widths=[1.5, 1.4, 0.6, 1.8, 1.7])
            if other_count:
                body(doc, f"{other_count} additional mechanism(s) checked and found current or "
                          f"unverified (no deduction).", 9.5, GRAY)
        else:
            msg = "No non-current mechanisms found in this lane."
            if other_count:
                msg += (f" ({other_count} mechanism(s) checked and found current or unverified.)")
            body(doc, msg, 9.5, GRAY)

    # ---- 5. In-house IP gaps ----
    section_head(doc, "5. In-house IP gaps are candidates for Zennify template expansion")
    ip = lists.get("in_house_ip_gaps", []) or []
    body(doc, f"Zennify-source criteria where ZenAgent scored Partial or Absent ({len(ip)} found). "
              f"Each names the evidence anchor (what the SDD did say) and the ZMS depth bar (what good requires).")
    _prov_za = (za.get("consensus_provenance") or {}) if dual else {}
    for r in ip:
        cid = r.get("zms_criterion_id", "")
        dimn = r.get("dimension", "")
        zav = r.get("za_verdict", ""); otsv = r.get("ots_verdict", "")
        sev = r.get("severity", "")
        fields = [("Evidence anchor.", r.get("za_anchor") or r.get("evidence_anchor") or "Not specified in the SDD.", DARK),
                  ("ZMS depth bar.", r.get("depth_indicator") or r.get("depth_bar") or "", TEAL)]
        # v4.7: judge provenance on the claim (FR-6/SM-4). Only non-agreed
        # criteria carry a badge line — agreed is the norm and stays quiet.
        _p = _prov_za.get(cid)
        if dual and _p and _p != "agreed":
            fields.append(("Judge provenance.",
                           f"{_p} — both judges' entries and the ruling evidence are in "
                           "Appendix D (Dissent & Reconciliation).", BLUE))
        card(doc, f"{cid}      Dimension {dimn}  .  ZenAgent {zav}  .  off-the-shelf {otsv}  .  severity {sev}",
             fields)
    if not ip:
        body(doc, "No in-house IP gaps: ZenAgent met every applicable Zennify-source criterion.", color=GRAY)

    # ---- 6. Agreement (dual-judge) / Variance (frozen five-pass) ----
    if dual:
        section_head(doc, "6. Cross-model agreement and confidence across the two judges")
        body(doc, "Each dimension was scored once by each judge — Claude and Gemini, two "
                  "unrelated model families — from byte-identical blinded packets. Agreement "
                  "between them is the reliability evidence: score concordance is 1 − |A−B| / "
                  "dimension max; the verdict agreement rate is matched verdicts over non-NA "
                  "criteria; a DISSENT marks a criterion the evidence-ruled reconciliation "
                  "could not settle (resolved conservatively; preserved verbatim in Appendix D).")
        for lane_name, b, agg in (("ZenAgent", za, agg_za), ("Off-the-shelf", ots, agg_ots)):
            body(doc, lane_name, 11, DARK, after=2)
            jr = b.get("judge_runs_by_dimension") or {}
            pda = b.get("per_dim_agreement") or {}
            rpd = agg.get("verdict_agreement_rate_per_dim") or {}
            ddims = _dissent_dims(b)
            rows = []
            for d in range(1, 8):
                ds = str(d)
                rows.append([f"D{d}", DIMNAMES[d],
                             fmt(_num((jr.get(_JA) or {}).get(ds))),
                             fmt(_num((jr.get(_JB) or {}).get(ds))),
                             fmt(_num((jr.get("consensus") or {}).get(ds))),
                             fmt(_num(pda.get(ds))), fmt(_num(rpd.get(ds))),
                             "DISSENT" if d in ddims else "clear"])
            data_table(doc, ["Dim", "Dimension", "Claude", "Gemini", "Consensus",
                             "Concordance", "Verdict agr.", "Dissent"],
                       rows, widths=[0.4, 1.5, 0.7, 0.7, 0.8, 0.9, 0.85, 0.75],
                       flag_col=7)
            body(doc, f"Lane summary: verdict agreement {fmt(_num(agg.get('verdict_agreement_rate')))} · "
                      f"score concordance {fmt(_num(agg.get('score_concordance')))} · "
                      f"agreement overall {fmt(_num(agg.get('agreement_overall')))} — "
                      f"{agg.get('reliability_label', '')} · "
                      f"{agg.get('divergence_count', 0)} divergence(s) reconciled · "
                      f"{agg.get('dissent_count', 0)} dissent(s) preserved.", 9.5, BLUE)
    else:
        section_head(doc, "6. Score variance and confidence across the five scoring passes")
        vflags = lists.get("variance_flags", []) or t.get("variance_flag_list", [])
        if vflags:
            body(doc, "Variance flags (sample stddev > 1.0 across the five passes): " +
                      ", ".join(str(v) for v in vflags) + ". A flag marks a dimension whose score was "
                      "less stable across passes and warrants a confirming read.")
        else:
            body(doc, "Variance flags (sample stddev > 1.0 across the five T=0.3 passes): none. All "
                      "dimension scores were stable across the five passes, so the bands are reported "
                      "with normal confidence.")

    # ---- 7. Refinement areas by lane (dual-judge; the review deliverable) ----
    # ADDITIVE section (operator direction, errata Q10): the report's actionable
    # spine — where each design needs refinement, on what evidence. The full
    # prioritized worklists remain verbatim in Appendix A; the priority cards
    # above carry the how-to-close depth. Nothing existing is reduced.
    if dual:
        section_head(doc, "7. Refinement areas by lane")
        body(doc, "Every dimension-level signal that calls for refinement work, per lane: "
                  "gate failures, below-baseline dimensions, release-currency deductions, "
                  "and cross-judge dissents (contested areas needing SA adjudication). Each "
                  "item traces to the scored evidence above; the prioritised worklist in "
                  "Appendix A carries the full audit trail.")
        for lane_name, key in (("ZenAgent", "section_5_2_za_review"),
                               ("Off-the-shelf", "section_5_2_ots_review")):
            items = bundle.get(key) or []
            body(doc, lane_name, 11, DARK, after=2)
            if not items:
                body(doc, "No refinement areas: every gated dimension cleared and no dissent, "
                          "deduction, or baseline regression touched this lane.", 9.5, GRAY)
                continue
            rows = [[r.get("priority", ""),
                     r.get("dim_name") or r.get("section", ""),
                     r.get("issue_type", ""),
                     str(r.get("notes") or "")[:110]] for r in items]
            data_table(doc, ["Priority", "Area", "Signal", "What the evidence says"],
                       rows, widths=[0.7, 1.6, 1.4, 3.1])

    # ---- APPENDIX (reference only) ----
    doc.add_paragraph().paragraph_format.space_before = Pt(8)
    label(doc, "Appendix . Supporting evidence")
    section_head(doc, "Appendix A. Prioritised SA review list")
    body(doc, "The full reviewer worklist, retained for audit. The decision and its rationale are in "
              "the body above; this list is reference only.", 9.5, GRAY)
    sa = []
    for pri in ("High", "Medium", "Low"):
        for r in (review_lists.get(pri, []) or []):
            if isinstance(r, dict):
                sa.append(r)
            elif isinstance(r, (list, tuple)) and len(r) >= 4:
                sa.append({"lane": r[0], "trigger": r[2] if len(r) > 2 else "",
                           "detail": r[2] if len(r) > 2 else "", "recommended_action": r[3] if len(r) > 3 else ""})
    if sa:
        rows = [[r.get("lane", ""), r.get("trigger", ""), (r.get("detail", "") or "")[:50],
                 (r.get("recommended_action", "") or "")[:50]] for r in sa]
        data_table(doc, ["Lane", "Trigger", "Detail", "Recommended action"], rows,
                   widths=[1.1, 1.4, 2.0, 2.0])

    # ---- provenance ----
    section_head(doc, "Appendix B. Run provenance")
    data_table(doc, ["Field", "Value"], [
        ["ZMS version", f"{t.get('zms_version','')} (frozen)"],
        ["Applicable criteria", str(t.get("zms_applicable_criteria_count", ""))],
        ["Applicability keys fired", str(t.get("applicability_keys_fired", ""))],
        ["Methodology version", str(t.get("methodology_version", ""))],
        ["Evaluator model", str(t.get("model_version", ""))],
        ["Run ID", str(t.get("run_id", ""))],
        ["BRD SHA-256", str(t.get("input_artefact_sha256", ""))[:40]],
    ], widths=[2.0, 4.5])

    # ---- Appendix C. ZMS coverage matrix (full criterion-level audit trail) ----
    cov = lists.get("zms_coverage_matrix", []) or []
    if cov:
        section_head(doc, "Appendix C. ZMS coverage matrix")
        body(doc, f"Every applicable ZMS criterion ({len(cov)} rows), with each lane's verdict and "
                  "the criterion source. This is the criterion-level audit trail behind the "
                  "per-dimension bands and the in-house IP-gap analysis above.", 9.5, GRAY)
        cov_rows = [[r.get("zms_criterion_id", r.get("criterion_id", "")),
                     (r.get("source", "") or "")[:22],
                     str(r.get("dimension", "")),
                     r.get("za_verdict", "—"),
                     r.get("ots_verdict", "—")] for r in cov]
        data_table(doc, ["Criterion", "Source", "Dim", "ZenAgent", "Off-the-shelf"],
                   cov_rows, widths=[1.7, 1.6, 0.5, 1.3, 1.3])

    # ---- Appendix D. Dissent & Reconciliation annex (dual-judge; FR-6) ----
    # EVERY divergence between the two judges, per lane: both judges' verdicts
    # and verbatim anchors, the evidence-ruled outcome, its SDD citation, and —
    # for dissents — why it could not be settled plus the conservative
    # resolution that stands in the scores. SM-4: 100% of divergences appear
    # here (validated upstream by R26/R27).
    if dual:
        section_head(doc, "Appendix D. Dissent & Reconciliation annex")
        body(doc, "The complete reconciliation record. Two independent judges scored every "
                  "criterion from byte-identical blinded packets; the items below are the ONLY "
                  "places they diverged. Rulings adopt one judge, meet between with stated "
                  "cause, or record a dissent — dissents resolve conservatively (weaker "
                  "verdict / lower score) and stand in the scores above. Nothing here was "
                  "averaged away.", 9.5, GRAY)
        for lane_name, b in (("ZenAgent", za), ("Off-the-shelf", ots)):
            entries = []
            for sub_key, blk in (b.get("content_coding") or {}).items():
                for comp in (blk.get("zms_components") or []):
                    if isinstance(comp, dict) and comp.get("provenance", "agreed") != "agreed":
                        entries.append(comp)
            dissents = b.get("dissents") or []
            why_by_cid = {dd.get("criterion_id"): dd.get("why_unresolved")
                          for dd in dissents if dd.get("criterion_id")}
            body(doc, f"{lane_name} — {len(entries)} reconciled criterion divergence(s), "
                      f"{len(dissents)} dissent record(s).", 11, DARK, after=2)
            if not entries and not dissents:
                body(doc, "The two judges agreed on every criterion and sub-criterion score "
                          "for this lane.", 9.5, GRAY)
                continue
            for comp in sorted(entries, key=lambda c: c.get("zms_criterion_id", "")):
                cid = comp.get("zms_criterion_id", "")
                prov = comp.get("provenance", "")
                je = comp.get("judge_entries") or {}
                ea, eb = je.get(_JA) or {}, je.get(_JB) or {}
                fields = [
                    ("Judge A (Claude).",
                     f"{ea.get('verdict', 'n/a')} — “{ea.get('evidence_anchor', '') or 'no anchor'}”"
                     f" ({ea.get('sdd_ref', '') or 'no ref'})", DARK),
                    ("Judge B (Gemini).",
                     f"{eb.get('verdict', 'n/a')} — “{eb.get('evidence_anchor', '') or 'no anchor'}”"
                     f" ({eb.get('sdd_ref', '') or 'no ref'})", DARK),
                ]
                if prov == "dissent":
                    fields.append(("Why unresolved.",
                                   why_by_cid.get(cid) or comp.get("ruling_rationale")
                                   or "recorded dissent", NEG))
                    fields.append(("Conservative resolution.",
                                   f"{comp.get('verdict', '')} — “{comp.get('evidence_anchor', '')}”",
                                   NEG))
                else:
                    fields.append(("Ruling.", f"{prov} — {comp.get('ruling_rationale') or ''}", TEAL))
                    if comp.get("ruling_citation"):
                        fields.append(("Ruling evidence (verbatim SDD).",
                                       f"“{comp.get('ruling_citation')}”", TEAL))
                    fields.append(("Consensus.",
                                   f"{comp.get('verdict', '')} — “{comp.get('evidence_anchor', '')}”",
                                   DARK))
                card(doc, f"{cid}   ·   {prov.upper()}", fields,
                     fill="fbf0ec" if prov == "dissent" else CARD_FILL)
            # sub-score level divergences (reconciled or dissented)
            sub_rows = []
            for d in range(1, 8):
                for key, e in (b.get(f"dim_{d}_sub_criteria") or {}).items():
                    if isinstance(e, dict) and e.get("provenance") not in (None, "agreed"):
                        sub_rows.append([f"D{d}", key.replace("_", " "),
                                         fmt(_num(e.get(_JA))), fmt(_num(e.get(_JB))),
                                         fmt(_num(e.get("consensus"))),
                                         e.get("provenance", "")])
            if sub_rows:
                body(doc, "Sub-criterion score divergences (beyond the 20%-of-max threshold):",
                     9.5, GRAY, after=2)
                data_table(doc, ["Dim", "Sub-criterion", "Claude", "Gemini", "Consensus", "Outcome"],
                           sub_rows, widths=[0.5, 2.1, 0.8, 0.8, 0.9, 1.3], flag_col=5)

    doc.save(args.output)
    print(json.dumps({"output": args.output, "za_band": za_band, "ots_band": ots_band,
                      "ots_ahead_dims": [d for d, *_ in ots_ahead]}, indent=2))


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def fmt(v):
    n = _num(v)
    return "" if n is None else (f"{n:.1f}" if abs(n - round(n)) > 0.001 else f"{n:.0f}" if abs(n) >= 1 else f"{n:.1f}")


def lift_phrase(lift, within_noise=False, neff=None):
    """Render the lift as a STATISTICAL statement, not a bare integer. When the
    pass-noise band spans zero (within_noise) or there is effectively ≤1
    independent pass (neff), the difference is not measurable and the phrase says
    so rather than asserting a point edge. The returned phrase includes the
    'off-the-shelf baseline' object so callers prepend only the subject."""
    s = str(lift)
    noisy = str(within_noise).lower() == "true"
    ne = None
    try:
        ne = float(neff) if neff not in (None, "") else None
    except Exception:
        ne = None
    if noisy or (ne is not None and ne < 1.5):
        return "showed no measurable difference from the off-the-shelf baseline (lift within pass noise)"
    if s.startswith("-"):
        return f"trailed the off-the-shelf baseline by {s[1:]} points"
    if s.startswith("+") and s != "+0":
        return f"gained {s} points over the off-the-shelf baseline"
    return "matched the off-the-shelf baseline"


def ots_win_reason(bundle, lists, dim):
    """Build a grounded 'why OTS won' from the coverage matrix for this dimension."""
    cov = lists.get("zms_coverage_matrix", []) or bundle.get("zms_coverage_matrix", []) or []
    wins = [r for r in cov if str(r.get("dimension")) == str(dim)
            and r.get("ots_verdict") in ("Present", "Partial")
            and r.get("za_verdict") in ("Absent", "Partial")
            and not (r.get("ots_verdict") == r.get("za_verdict"))]
    if wins:
        bits = []
        for r in wins[:2]:
            cid = r.get("zms_criterion_id", r.get("criterion_id", ""))
            anchor = (r.get("ots_anchor") or "")[:80]
            bits.append(f"{cid}: off-the-shelf {r.get('ots_verdict')} vs ZenAgent {r.get('za_verdict')}"
                        + (f" ({anchor})" if anchor else ""))
        return "Off-the-shelf coded higher on " + "; ".join(bits) + "."
    # No criterion-level win rows for this dimension. Do NOT imply detail exists
    # elsewhere (QA-03: fail honest, not silent). If the matrix is entirely empty
    # the caller surfaces a population warning; here we state the truth plainly.
    if not cov:
        return ("Criterion-level coverage detail was not available to this report "
                "(coverage matrix unpopulated); the dimension-level lift is shown above.")
    return ("On this dimension the two lanes coded at the same criterion level; "
            "the lift reflects sub-criterion scoring rather than a coverage gap.")


if __name__ == "__main__":
    sys.exit(main())
