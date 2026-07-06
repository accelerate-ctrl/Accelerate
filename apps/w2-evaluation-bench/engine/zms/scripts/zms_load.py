#!/usr/bin/env python3
"""
zms_load.py — ZMS skill invocation entry point.

Consumes applicability flags + run_id from the calling skill (evaluate-sdd Section B),
filters the 99 ZMS criteria to those that fire for this engagement, and emits
the zms-calibration-content.json that Section D consumes.

This is the loader that REPLACES the Benchmark Library lookup in the original
workflow. The output has the same role in the pipeline as the old
`benchmark-pair-content.json` — but the content is a frozen calibration
reference, not a paired exemplar from a Library.

Usage (CLI):
    python3 zms_load.py \\
        --applicability '{"integration_heavy": true, "multi_cloud": false, ...}' \\
        --run-id W2-2026-06-03-xxxxxxxx \\
        --output-dir /pilot-runs/<run_id>/

Or via stdin (preferred by orchestrator):
    echo '{"applicability": {...}, "run_id": "..."}' | python3 zms_load.py --stdin --output-dir ...

Outputs:
    <output-dir>/zms-calibration-content.json   (calibration bar for this engagement)
    <output-dir>/zms-calibration-summary.json   (cover-panel provenance fields)

Exit codes:
    0 = success
    2 = invalid input (missing fields, malformed JSON)
    3 = ZMS data file not found / corrupt
    4 = output directory not writable
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

# Resolve the ZMS skill's data directory relative to this script.
# Skill layout: <skill_root>/scripts/zms_load.py and <skill_root>/data/zms-criteria.json
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
DATA_PATH = SKILL_ROOT / "data" / "zms-criteria.json"
MAPPING_PATH = SKILL_ROOT / "data" / "zms-22-mapping.json"
PLAYBOOK_PATH = SKILL_ROOT / "references" / "sa-reasoning-playbook.md"

# Recognised applicability keys — must match the ZMS criteria's `applicability` field
RECOGNISED_FLAGS = {
    "ALL",                 # always-on (every criterion with applicability=ALL fires)
    "INTEGRATIONS",        # 4+ material integration points (integration_heavy)
    "EXTERNAL_USERS",      # Experience Cloud / portal in scope
    "REGULATED",           # regulated industry (FSI, healthcare, gov, etc.)
    "REGULATORY_CITATION", # specific regulatory citations expected
    "AUTOMATION",          # business automation in scope
    "TRIGGERS",            # Apex triggers in scope
    "CUSTOM_BUILD",        # custom-built components (LWC/Apex) in scope
    "UI_IN_SCOPE",         # UI work in scope
    "MULTI_CLOUD",         # 2+ Salesforce clouds in scope
    "CONFIG_DRIVEN",       # configuration-heavy engagement
    "API",                 # external API consumption in scope
    "DATA_MIGRATION",      # data migration in scope
    "PHASING",             # phased delivery in scope
}


def load_zms_data() -> tuple[dict, dict]:
    """Load and validate the ZMS data files. Raise on corruption."""
    if not DATA_PATH.exists():
        print(f"FATAL: ZMS data file not found at {DATA_PATH}", file=sys.stderr)
        sys.exit(3)
    if not MAPPING_PATH.exists():
        print(f"FATAL: ZMS mapping file not found at {MAPPING_PATH}", file=sys.stderr)
        sys.exit(3)

    try:
        zms_data = json.loads(DATA_PATH.read_text())
        mapping = json.loads(MAPPING_PATH.read_text())
    except json.JSONDecodeError as e:
        print(f"FATAL: ZMS data file malformed: {e}", file=sys.stderr)
        sys.exit(3)

    if "criteria" not in zms_data or not isinstance(zms_data["criteria"], list):
        print("FATAL: ZMS data file missing 'criteria' array", file=sys.stderr)
        sys.exit(3)

    return zms_data, mapping


def applicability_fires(criterion_applies: str, flags: dict[str, bool]) -> bool:
    """Return True if the criterion fires given the engagement's flags.

    `criterion_applies` is one of the RECOGNISED_FLAGS values (single key
    per criterion in v1.0.0 — multi-flag boolean logic is reserved for v1.1.0
    if required).
    """
    if criterion_applies == "ALL":
        return True
    return bool(flags.get(criterion_applies, False))


def filter_criteria(criteria: list[dict], flags: dict[str, bool]) -> list[dict]:
    """Return only the criteria that fire given the engagement's flags."""
    return [c for c in criteria if applicability_fires(c["applicability"], flags)]


def build_calibration_content(zms_data: dict, mapping: dict,
                              applicable: list[dict], run_id: str,
                              flags: dict[str, bool]) -> dict:
    """Assemble the Section-D-consumable calibration bundle."""
    # Group applicable criteria by dimension and sub-criterion
    by_dim: dict[str, dict[str, list[str]]] = {}
    for c in applicable:
        dim = str(c["dimension"])
        sub = c["parent_sub_criterion"]
        by_dim.setdefault(dim, {}).setdefault(sub, []).append(c["id"])

    # Sort the lists for stable output
    for dim in by_dim:
        for sub in by_dim[dim]:
            by_dim[dim][sub].sort()

    src_dist = Counter(c["source"] for c in applicable)
    critical_floor_active = [c["id"] for c in applicable if c["critical_floor"]]

    return {
        "schema_version": "1.0.0",
        "zms_version": zms_data["zms_version"],
        "zms_frozen_at": zms_data["frozen_at"],
        "run_id": run_id,
        "applicability_flags": flags,
        "applicable_criteria": applicable,
        "criteria_by_dim_and_sub": by_dim,
        "summary": {
            "applicable_criteria_count": len(applicable),
            "total_criteria_in_register": len(zms_data["criteria"]),
            "criteria_by_source": dict(src_dist),
            "critical_floor_active": critical_floor_active,
            "critical_floor_count": len(critical_floor_active),
            "applicability_keys_fired": sorted([k for k, v in flags.items() if v]),
        },
        "sa_reasoning_playbook_path": str(PLAYBOOK_PATH),
        "sub_criteria_mapping": mapping["mapping"],
    }


def build_summary(calibration: dict) -> dict:
    """Cover-panel provenance summary — small, surfaceable in §4 of the report."""
    s = calibration["summary"]
    return {
        "schema_version": "1.0.0",
        "zms_version": calibration["zms_version"],
        "zms_frozen_at": calibration["zms_frozen_at"],
        "run_id": calibration["run_id"],
        "applicable_criteria_count": s["applicable_criteria_count"],
        "criteria_by_source": s["criteria_by_source"],
        "critical_floor_active": s["critical_floor_active"],
        "applicability_keys_fired": s["applicability_keys_fired"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="ZMS loader — emit calibration bundle for Section D")
    parser.add_argument("--applicability", help="JSON object of applicability flags")
    parser.add_argument("--run-id", help="Run ID (e.g. W2-2026-06-03-xxxxxxxx)")
    parser.add_argument("--output-dir", required=True,
                        help="Where to write zms-calibration-content.json and -summary.json")
    parser.add_argument("--stdin", action="store_true",
                        help="Read {applicability, run_id} JSON from stdin")
    args = parser.parse_args()

    # Resolve inputs
    if args.stdin:
        try:
            payload = json.load(sys.stdin)
        except json.JSONDecodeError as e:
            print(f"ERROR: stdin not valid JSON: {e}", file=sys.stderr)
            return 2
        flags = payload.get("applicability", {})
        run_id = payload.get("run_id", "")
    else:
        if not args.applicability or not args.run_id:
            print("ERROR: must provide --applicability and --run-id (or use --stdin)",
                  file=sys.stderr)
            return 2
        try:
            flags = json.loads(args.applicability)
        except json.JSONDecodeError as e:
            print(f"ERROR: --applicability not valid JSON: {e}", file=sys.stderr)
            return 2
        run_id = args.run_id

    if not isinstance(flags, dict) or not run_id:
        print("ERROR: applicability must be object; run_id must be non-empty string",
              file=sys.stderr)
        return 2

    # Validate flag keys against the recognised set
    unknown = set(flags.keys()) - RECOGNISED_FLAGS
    if unknown:
        print(f"WARNING: unrecognised applicability flags will be ignored: {sorted(unknown)}",
              file=sys.stderr)

    # Coerce string booleans for friendliness ("true"/"false" -> bool)
    coerced = {}
    for k, v in flags.items():
        if isinstance(v, str):
            coerced[k] = v.lower() in ("true", "yes", "1")
        else:
            coerced[k] = bool(v)
    flags = coerced

    # Output directory
    out_dir = Path(args.output_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"ERROR: cannot create output dir {out_dir}: {e}", file=sys.stderr)
        return 4

    # Load and filter
    zms_data, mapping = load_zms_data()
    applicable = filter_criteria(zms_data["criteria"], flags)

    calibration = build_calibration_content(zms_data, mapping, applicable, run_id, flags)
    summary = build_summary(calibration)

    # Write outputs
    cal_path = out_dir / "zms-calibration-content.json"
    sum_path = out_dir / "zms-calibration-summary.json"
    cal_path.write_text(json.dumps(calibration, indent=2, ensure_ascii=False))
    sum_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    # Emit digest to stdout (for orchestrator capture)
    digest = {
        "status": "ok",
        "run_id": run_id,
        "zms_version": calibration["zms_version"],
        "applicable_criteria_count": calibration["summary"]["applicable_criteria_count"],
        "criteria_by_source": calibration["summary"]["criteria_by_source"],
        "critical_floor_active_count": calibration["summary"]["critical_floor_count"],
        "applicability_keys_fired": calibration["summary"]["applicability_keys_fired"],
        "calibration_content_path": str(cal_path),
        "calibration_summary_path": str(sum_path),
        "sa_reasoning_playbook_path": calibration["sa_reasoning_playbook_path"],
    }
    print(json.dumps(digest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
