#!/usr/bin/env python3
"""make_template_v47.py — generate score-sheet-template-v4.7.xlsx from the
frozen v4.6 template, mechanically and auditably (run this script; diff the
output; commit both).

Why a generated asset instead of hand-editing: the five-pass shape lives in
FOUR template surfaces (errata V-3) — the Dim_1-7 pass columns + Mean formula,
the Variance_Record five-run matrices, the Cover R1–R25 checklist, and the
sheet header prose. A scripted transformation guarantees the v4.7 sheet drifts
from v4.6 ONLY in the places the protocol change requires, and the attestation
cells are set from contracts verbatim (the v4.6 template's static attestation
text had drifted from contracts — display-only, fixed here at the source).

The v4.6 template file is NOT touched: it remains the asset for the frozen
EVAL_PROTOCOL=five-pass regression path.
"""
from __future__ import annotations

import sys
from pathlib import Path

from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contracts

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets"
SRC = ASSETS / "score-sheet-template-v4.6.xlsx"
DST = ASSETS / "score-sheet-template-v4.7.xlsx"

# Sub-criterion ids in template row order on Dim_1-7_Sub_Criteria (col B).
NEW_RULE_ROWS = [
    ("R26", "{{R26_result}}",
     "Every applicable criterion has consensus_provenance; every non-agreed "
     "provenance carries judge_entries + (ruling citation or dissent)"),
    ("R27", "{{R27_result}}",
     "Dissent integrity: conservative_resolution is the weaker verdict / lower "
     "score of the two judges; every dissent ruling appears exactly once in dissents"),
    ("R28", "{{R28_result}}",
     "judge_independence_attestation verbatim; judge_runs_by_dimension contains "
     "exactly the two configured judges + consensus"),
]


def build() -> Path:
    wb = load_workbook(SRC)

    # ---------------- Cover ----------------
    ws = wb["Cover"]
    ws.cell(3, 2).value = ("v4.7 (rubric) · score sheet for evaluate-sdd v4.7 · "
                           "ZMS v4.6 · dual-judge consensus")
    ws.cell(4, 2).value = ("rubric v4.7 §8 (R1, R3–R28; R2 retired under dual-judge); "
                           "OH v4.7 §3.8, §4")
    ws.cell(6, 2).value = ("output-{a|b}-scoring-bundle.json (after 28-rule bundle "
                           "validation per rubric §8 / OH §3.8.1)")
    ws.cell(34, 1).value = ("Bundle validation (R1–R28 — rubric §8 / OH §3.8.1; "
                            "R2 retired under dual-judge)")
    # Re-pointed rule descriptions (rows fixed in the v4.6 layout).
    ws.cell(37, 3).value = ("retired under dual-judge (five-run arrays are a "
                            "five-pass-protocol structure)")
    ws.cell(38, 3).value = ("consensus per-dim recomputation (Σ consensus sub-scores; "
                            "Dim-3 net of capped deductions, floor 0; Dim-4 floored)")
    ws.cell(39, 3).value = ("per-judge totals present and numeric for both judges "
                            "on all 7 dims; consensus inside the judges' envelope")
    ws.cell(40, 3).value = ("agreement fields consistent with judge values "
                            "(per_dim_agreement = 1 − |A−B|/dim_max; agreement_stats coherent)")
    ws.cell(49, 3).value = ("Blinding-leak scan (reasoning, anchors, AND reconcile "
                            "ruling_citation / ruling_rationale / dissent records)")
    ws.cell(60, 3).value = ("Evidence-anchor groundedness + criterion relevance — applied "
                            "to consensus citations, BOTH judges' retained anchors, and "
                            "every reconcile ruling citation (R25b/c/e provable when "
                            "source index supplied)")

    # Insert R26–R28 rows after R25 (row 60); the attestation block shifts down.
    ws.insert_rows(61, len(NEW_RULE_ROWS))
    for i, (rule, token, detail) in enumerate(NEW_RULE_ROWS):
        ws.cell(61 + i, 1).value = rule
        ws.cell(61 + i, 2).value = token
        ws.cell(61 + i, 3).value = detail
    att_header_row = 61 + len(NEW_RULE_ROWS)          # was 61
    ws.cell(att_header_row, 1).value = (
        "Attestations (R15, R16, R28 — must match template verbatim)")
    # Attestation texts set from contracts VERBATIM (single source of truth).
    ws.cell(att_header_row + 1, 1).value = "Non-bias attestation"
    ws.cell(att_header_row + 1, 2).value = contracts.NON_BIAS_ATTESTATION
    ws.cell(att_header_row + 2, 1).value = "Blinding attestation"
    ws.cell(att_header_row + 2, 2).value = contracts.BLINDING_ATTESTATION
    ws.cell(att_header_row + 3, 1).value = "Judge-independence attestation"
    ws.cell(att_header_row + 3, 2).value = contracts.JUDGE_INDEPENDENCE_ATTESTATION

    # Judge model provenance rows (Run metadata block; insert after model_version
    # row 14 — done LAST on this sheet so the fixed row numbers above stay valid).
    ws.insert_rows(15, 2)
    ws.cell(15, 1).value = "judge_a_model"
    ws.cell(15, 2).value = "{{judge_a_model}}"
    ws.cell(15, 3).value = "Judge A — Claude Code model version (header.judge_models)"
    ws.cell(16, 1).value = "judge_b_model"
    ws.cell(16, 2).value = "{{judge_b_model}}"
    ws.cell(16, 3).value = "Judge B — Gemini model (header.judge_models)"

    # ---------------- Per_Dimension_Scoring ----------------
    ws = wb["Per_Dimension_Scoring"]
    ws.cell(2, 1).value = (
        "Per-dimension score = the dual-judge CONSENSUS value: each judge scores "
        "once from a byte-identical blinded packet; divergences are reconciled on "
        "cited SDD evidence; dissents resolve conservatively and are listed in the "
        "report's Dissent & Reconciliation annex. Final per-dim score = consensus "
        "after deductions (Dim 3) and floor (Dim 4). 80% gate per rubric §8; band "
        "per rubric §3. Dissent flag marks dimensions touched by a recorded dissent.")

    # ---------------- Dim_1-7_Sub_Criteria ----------------
    ws = wb["Dim_1-7_Sub_Criteria"]
    ws.cell(2, 1).value = (
        "21 sub-criteria across 7 dimensions (22 if multi_cloud=true — adds 3E). "
        "Each row records Judge A (Claude) and Judge B (Gemini) — each an "
        "independent cold read from a byte-identical blinded packet — the "
        "consensus value, and its provenance (agreed / adopt_claude / adopt_gemini "
        "/ meet_between / dissent). Dissent consensus is the conservative minimum; "
        "the reasoning excerpt carries the audit trail. Sub-criterion max varies "
        "with multi_cloud (Dim 3); Dim-5/7 weight swap (integration_heavy) applies "
        "at dimension level.")
    hdr = {5: "Judge A (Claude)", 6: "Judge B (Gemini)", 7: "Consensus",
           8: "Provenance", 9: None, 10: "Score (= consensus)"}
    for col, text in hdr.items():
        ws.cell(4, col).value = text
    for r in range(5, ws.max_row + 1):
        sid = ws.cell(r, 2).value
        if not isinstance(sid, str) or not sid.strip():
            continue
        sid = sid.strip()
        ws.cell(r, 5).value = "{{%s_cc}}" % sid
        ws.cell(r, 6).value = "{{%s_gm}}" % sid
        ws.cell(r, 7).value = "{{%s_con}}" % sid
        ws.cell(r, 8).value = "{{%s_prov}}" % sid
        ws.cell(r, 9).value = None
        ws.cell(r, 10).value = '=IFERROR(G%d,"")' % r

    # ---------------- Variance_Record -> Judge_Record ----------------
    ws = wb["Variance_Record"]
    ws.title = "Judge_Record"
    ws.cell(1, 1).value = "Judge Record — Dual-Judge Dimension Scores & Agreement"
    ws.cell(2, 1).value = (
        "One row per dimension: each judge's post-adjustment total (Dim-3 net of "
        "capped deductions, Dim-4 floored — applied identically to both judges and "
        "the consensus), the consensus total, the score concordance "
        "(1 − |A−B| / dim max), the per-dimension verdict agreement rate, and the "
        "dissent flag (set iff a recorded dissent touches the dimension). "
        "Cross-model disagreement is reported, never averaged away: dissents "
        "resolve conservatively and are itemised in the report annex.")
    heads = {3: "Judge A (Claude)", 4: "Judge B (Gemini)", 5: "Consensus",
             6: "Score concordance", 7: "Verdict agreement", 8: "Dissent flag",
             9: None, 10: None}
    for col, text in heads.items():
        ws.cell(4, col).value = text
    for dim in range(1, 8):
        r = 4 + dim
        ws.cell(r, 3).value = "{{dim_%d_judge_cc}}" % dim
        ws.cell(r, 4).value = "{{dim_%d_judge_gm}}" % dim
        ws.cell(r, 5).value = "{{dim_%d_con}}" % dim
        ws.cell(r, 6).value = "{{dim_%d_conc}}" % dim
        ws.cell(r, 7).value = "{{dim_%d_agree_rate}}" % dim
        ws.cell(r, 8).value = "{{dim_%d_dissent}}" % dim
        ws.cell(r, 9).value = None
        ws.cell(r, 10).value = None
    # Agreement summary block (consumed verbatim by checkpoint/report readers).
    ws.cell(13, 1).value = "Agreement summary (Backend Schema §6.5; computed once, TR-21)"
    rows = [("verdict_agreement_rate", "{{agree_rate_overall}}",
             "matched verdicts / non-NA criteria, both dim-groups"),
            ("score_concordance", "{{concordance_overall}}",
             "dim_max-weighted mean of per-dimension concordance"),
            ("agreement_overall", "{{agreement_overall}}",
             "0.5 · verdict_agreement_rate + 0.5 · score_concordance"),
            ("reliability", "{{reliability_label}}",
             "≥0.85 strong cross-model concurrence · 0.70–0.85 moderate · <0.70 weak"),
            ("dissent_count", "{{dissent_count}}",
             "criterion / sub-score dissents preserved in the annex"),
            ("divergence_count", "{{divergence_count}}",
             "items that required evidence-ruled reconciliation")]
    for i, (label, token, note) in enumerate(rows):
        ws.cell(14 + i, 1).value = label
        ws.cell(14 + i, 2).value = token
        ws.cell(14 + i, 3).value = note

    wb.save(DST)
    return DST


if __name__ == "__main__":
    out = build()
    print(f"wrote {out}")
