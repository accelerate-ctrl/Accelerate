#!/usr/bin/env python3
"""
content_mapping_classify.py (v2) — Section C helper.

Changes from v1:
- Now populates content-mapping.xlsx from the template (was: JSON-only)
- Writes section-c-output.json to disk (was: stdout only)
- Supports both SDDs (Output A and Output B) in one workbook

Inputs:
    --components-json   per-SDD components JSON
    --blinding-label    "Output A" or "Output B"
    --template          <knowledge-base>/content-mapping-template-v4.6.xlsx
    --workbook          /pilot-runs/<run_id>/content-mapping.xlsx (created or updated)
    --output            /pilot-runs/<run_id>/section-c-output-<a|b>.json

Returns JSON to stdout. Exit 0 on success.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

# contracts.py lives in this same scripts/ directory (single source of truth
# for the Dimension-4 floor-cap schedule).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import contracts

try:
    from openpyxl import load_workbook
except ImportError:
    print("ERROR: pip install openpyxl --break-system-packages", file=sys.stderr)
    sys.exit(10)


THE_EIGHT_REQUIRED = [
    "Scope and Assumptions",
    "Data Model",
    "Business Process Flows",
    "Security and Sharing Model",
    "Integration Architecture",
    "Reporting and Analytics Design",
    "Open Decisions Log",
    "Confidence Annotations",
]


def _get_decisions(comp: dict) -> int:
    """Tolerant accessor: accepts decisions_named OR decisions_named_count."""
    value = comp.get("decisions_named")
    if value is None:
        value = comp.get("decisions_named_count")
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _get_name(comp: dict) -> str | None:
    """Tolerant accessor: accepts name OR component_name."""
    return comp.get("name") or comp.get("component_name")


def classify_component(comp: dict) -> str:
    """OH §3.5.1 stub rule. ALL THREE must hold for Stub:
       under 200 substantive words AND fewer than 2 distinct decisions AND no mechanism named.
       Borderline defaults to Substantive. Recorded Classification overrides rule-derived.
    """
    recorded = comp.get("recorded_classification")
    if recorded in ("Substantive", "Stub", "Missing"):
        return recorded

    word_count = int(comp.get("word_count", 0) or 0)
    decisions_named = _get_decisions(comp)
    mechanism_named = (comp.get("mechanism_named") or "").strip()

    if word_count == 0 and decisions_named == 0 and not mechanism_named:
        return "Missing"

    if word_count < 200 and decisions_named < 2 and not mechanism_named:
        return "Stub"

    return "Substantive"


def classify_confidence_annotations(comp: dict) -> str:
    """OH §3.5.1 v1.4 adaptation for Confidence Annotations."""
    recorded = comp.get("recorded_classification")
    if recorded in ("Substantive", "Stub", "Missing"):
        return recorded

    word_count = int(comp.get("word_count", 0) or 0)
    annotation_entries = _get_decisions(comp)
    tied_to_sections = (comp.get("mechanism_named") or "").strip()

    if word_count == 0 and annotation_entries == 0 and not tied_to_sections:
        return "Missing"
    if word_count < 200 and annotation_entries < 2 and not tied_to_sections:
        return "Stub"
    return "Substantive"


def compute_floor_cap(stub_missing_count: int):
    """Dimension-4 floor cap per rubric section 6.4.1, read from the single
    source of truth in contracts.dim_4_floor_cap (0 -> no cap; 1-2 -> 10;
    3+ -> 7). Count 2 caps at 10 (the prior count==2 -> 7 hard-coding was a
    defect, fixed in v4.2)."""
    return contracts.dim_4_floor_cap(stub_missing_count)


def default_template_path(filename: str) -> Path:
    """Resolve a bundled template shipped in the skill's assets/ folder.
    The skill installs via Customize and keeps assets/ as real files on disk,
    so templates travel with the skill rather than the text-extraction KB."""
    return Path(__file__).resolve().parent.parent / "assets" / filename


def populate_content_mapping_xlsx(workbook_path: Path, template_path: Path,
                                  blinding_label: str,
                                  classifications: list[dict],
                                  floor_cap, stub_missing_count: int) -> None:
    """Populate content-mapping.xlsx for one lane (v3.1).

    The v3 template ships pre-built per-lane sheets so nothing is cloned or
    deleted at runtime (which previously orphaned the Floor_Calculation
    formulas). For lane X (A or B) this fills:
      Component_Classification_X  cols D-H, rows 5-15  (grid)
      Stub_Detection_Audit_X      cols C-G, rows 5-12  (three-criteria trail)
    Floor_Calculation_X is formula-driven off Component_Classification_X and
    recomputes automatically — this function never writes to it.
    """
    if not workbook_path.exists():
        shutil.copyfile(template_path, workbook_path)

    wb = load_workbook(workbook_path)
    lane = blinding_label[-1]  # "A" or "B"
    cls_sheet = f"Component_Classification_{lane}"
    audit_sheet = f"Stub_Detection_Audit_{lane}"
    if cls_sheet not in wb.sheetnames:
        raise SystemExit(f"ERROR: template missing sheet {cls_sheet}; regenerate template")

    ws = wb[cls_sheet]
    ws.cell(row=2, column=1,
            value=(f"Per-component classification for {blinding_label} "
                   f"(blinded; lane identity revealed only at Section G)."))

    # Rows 5-15 match the template's component order (8 required, 2 conditional, 1 optional)
    template_row_by_name = {
        "Scope and Assumptions": 5,
        "Data Model": 6,
        "Business Process Flows": 7,
        "Security and Sharing Model": 8,
        "Integration Architecture": 9,
        "Reporting and Analytics Design": 10,
        "Open Decisions Log": 11,
        "Confidence Annotations": 12,
        "Data Migration Approach": 13,
        "Phasing and Delivery Plan": 14,
        "Executive Summary": 15,
    }

    audit = wb[audit_sheet] if audit_sheet in wb.sheetnames else None

    for cls in classifications:
        name = cls.get("name")
        row = template_row_by_name.get(name)
        if row is None:
            continue
        word_count = cls.get("word_count")
        decisions = cls.get("decisions_named")
        mechanism = (cls.get("mechanism_named") or "").strip()
        classification = cls.get("classification")
        evidence = cls.get("sdd_location") or ""

        # Col D=word count, E=decisions, F=mechanism (Y/N), G=classification, H=evidence
        ws.cell(row=row, column=4, value=word_count)
        ws.cell(row=row, column=5, value=decisions)
        ws.cell(row=row, column=6, value="Y" if mechanism else "N")
        ws.cell(row=row, column=7, value=classification)
        ws.cell(row=row, column=8, value=evidence)

        # Three-criteria stub audit (only the 8 required components, rows 5-12)
        if audit is not None and 5 <= row <= 12:
            wc = int(word_count or 0)
            dc = int(decisions or 0)
            audit.cell(row=row, column=3, value="Y" if wc < 200 else "N")        # word < 200?
            audit.cell(row=row, column=4, value="Y" if dc < 2 else "N")          # < 2 decisions?
            audit.cell(row=row, column=5, value="Y" if not mechanism else "N")   # no SF mechanism?
            audit.cell(row=row, column=6, value="Y" if classification == "Stub" else "N")
            audit.cell(row=row, column=7,
                       value=(evidence if classification in ("Stub", "Missing")
                              else "n/a (Substantive)"))

    # Per-lane summary below the component rows (rows 17-19)
    ws.cell(row=17, column=1, value="Per-lane summary")
    ws.cell(row=18, column=1, value="stub_missing_count")
    ws.cell(row=18, column=2, value=stub_missing_count)
    ws.cell(row=19, column=1, value="dim_4_floor_cap")
    ws.cell(row=19, column=2, value=floor_cap if floor_cap is not None else "no cap")

    wb.save(workbook_path)



def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--components-json", required=True, type=Path)
    ap.add_argument("--blinding-label", required=True,
                    choices=["Output A", "Output B"])
    ap.add_argument("--template", type=Path, default=None,
                    help="Path to content-mapping-template-v4.6.xlsx. Defaults to the copy bundled in the skill's assets/ folder.")
    ap.add_argument("--workbook", required=True, type=Path,
                    help="Path to the run's content-mapping.xlsx (created if missing)")
    ap.add_argument("--output", required=True, type=Path,
                    help="Path to write section-c-output-<a|b>.json")
    args = ap.parse_args()
    if args.template is None:
        args.template = default_template_path("content-mapping-template-v4.6.xlsx")

    with open(args.components_json, encoding="utf-8") as f:
        data = json.load(f)

    components = data.get("components", [])
    classifications = []
    stub_missing_count = 0

    for comp in components:
        name = _get_name(comp)
        status_required = comp.get("status_required", "always")

        if name == "Confidence Annotations":
            cls = classify_confidence_annotations(comp)
        else:
            cls = classify_component(comp)

        classifications.append({
            "name": name,
            "status_required": status_required,
            "classification": cls,
            "sdd_location": comp.get("sdd_location"),
            "word_count": comp.get("word_count"),
            "decisions_named": _get_decisions(comp),
            "mechanism_named": comp.get("mechanism_named"),
        })

        if name in THE_EIGHT_REQUIRED and cls in ("Stub", "Missing"):
            stub_missing_count += 1

    floor_cap = compute_floor_cap(stub_missing_count)

    # Populate xlsx
    args.workbook.parent.mkdir(parents=True, exist_ok=True)
    populate_content_mapping_xlsx(
        args.workbook, args.template, args.blinding_label,
        classifications, floor_cap, stub_missing_count
    )

    result = {
        "blinding_label": args.blinding_label,
        "classifications": classifications,
        "stub_missing_count_over_8_required": stub_missing_count,
        "dim_4_floor_cap": floor_cap,
        "rule_applied": "OH §3.5.1 stub-detection ALL-THREE-CRITERIA; OH §3.5.2 floor",
        "content_mapping_workbook": str(args.workbook),
    }

    # Write section-c-output.json
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
