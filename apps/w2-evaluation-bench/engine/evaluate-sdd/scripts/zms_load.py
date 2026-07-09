#!/usr/bin/env python3
"""
zms_load.py — Section B of evaluate-sdd v4.6.

Thin shim that invokes the sibling ZMS skill's `zms_load.py` via subprocess.
Replaces v3.6's `benchmark_select.py`.

Composition contract (one-way): evaluate-sdd Section B → ZMS skill loader.
This shim does NOT contain calibration content; ZMS owns the criteria register.
This shim's job is:
  - Resolve the ZMS skill's location (next to evaluate-sdd, sibling skill)
  - Derive the applicability flags from intake-validate output
  - Invoke ZMS loader with {applicability, run_id}
  - Verify the digest came back ok
  - Place the calibration files where Section D can find them

Usage (CLI):
    python3 zms_load.py \\
        --intake-output /pilot-runs/<run_id>/section-a-output.json \\
        --run-id W2-2026-06-03-xxxxxxxx \\
        --output-dir /pilot-runs/<run_id>/ \\
        --zms-skill-root /path/to/zms-skill

Or via stdin (preferred):
    echo '{"intake_output_path": "...", "run_id": "...", "zms_skill_root": "..."}' \\
        | python3 zms_load.py --stdin --output-dir /pilot-runs/<run_id>/

Outputs:
    <output-dir>/zms-calibration-content.json   (consumed by Section D)
    <output-dir>/zms-calibration-summary.json   (consumed by Section G §4)
    Digest JSON to stdout (for orchestrator capture)

Exit codes:
    0 = success
    2 = invalid input (section-a-output.json malformed, run_id missing)
    3 = ZMS skill not found at given root, or self-test fails
    4 = ZMS loader returned non-zero
    5 = output directory not writable
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# 13 applicability flags consumed by ZMS criteria (the keys ZMS knows about).
# Intake-validate produces all of these as booleans. Intake should match this set
# 1:1; mismatches are surfaced as warnings.
EXPECTED_FLAGS = [
    "INTEGRATIONS", "EXTERNAL_USERS", "REGULATED", "REGULATORY_CITATION",
    "AUTOMATION", "TRIGGERS", "CUSTOM_BUILD", "UI_IN_SCOPE", "MULTI_CLOUD",
    "CONFIG_DRIVEN", "API", "DATA_MIGRATION", "PHASING",
]


def find_zms_skill_root(supplied: str | None) -> Path:
    """Locate the ZMS skill directory.

    Resolution order:
      1. --zms-skill-root if provided
      2. ZMS_SKILL_ROOT environment variable
      3. Sibling directory of evaluate-sdd skill (../zms/)
      4. /mnt/skills/user/zms/ (production deployment path)
      5. /mnt/skills/organization/zms/ (alternate deployment path)
    """
    candidates: list[Path] = []
    if supplied:
        candidates.append(Path(supplied))
    if "ZMS_SKILL_ROOT" in os.environ:
        candidates.append(Path(os.environ["ZMS_SKILL_ROOT"]))
    # Sibling of this script's skill (../zms/ relative to evaluate-sdd's scripts/)
    here = Path(__file__).resolve()
    candidates.append(here.parent.parent.parent / "zms")
    candidates.append(Path("/mnt/skills/user/zms"))
    candidates.append(Path("/mnt/skills/organization/zms"))

    for c in candidates:
        loader = c / "scripts" / "zms_load.py"
        register = c / "data" / "zms-criteria.json"
        if loader.exists() and register.exists():
            return c
    raise FileNotFoundError(
        f"ZMS skill not found. Tried: {[str(c) for c in candidates]}"
    )


def derive_applicability(intake: dict) -> dict[str, bool]:
    """Pull applicability flags from intake-validate output.

    Intake's `applicability_flags` dict is the canonical source. If intake is from
    a v3.6 era output without flags, derive from intake fields with sensible defaults.
    """
    if "applicability_flags" in intake and isinstance(intake["applicability_flags"], dict):
        flags = {k: bool(v) for k, v in intake["applicability_flags"].items()}
    else:
        # Fallback derivation from legacy intake fields (for backward compat)
        flags = {
            "INTEGRATIONS": bool(intake.get("integration_count", 0) >= 4),
            "EXTERNAL_USERS": bool(intake.get("experience_cloud_in_scope", False)),
            "REGULATED": bool(intake.get("regulated_industry", False)),
            "REGULATORY_CITATION": bool(intake.get("regulatory_citations_present", False)),
            "AUTOMATION": bool(intake.get("automation_in_scope", True)),
            "TRIGGERS": bool(intake.get("apex_triggers_in_scope", False)),
            "CUSTOM_BUILD": bool(intake.get("custom_components_in_scope", False)),
            "UI_IN_SCOPE": bool(intake.get("ui_in_scope", True)),
            "MULTI_CLOUD": bool(intake.get("multi_cloud", False)),
            "CONFIG_DRIVEN": bool(intake.get("config_driven", False)),
            "API": bool(intake.get("api_consumption", False)),
            "DATA_MIGRATION": bool(intake.get("data_migration", False)),
            "PHASING": bool(intake.get("phased_delivery", True)),
        }

    # Ensure all expected keys present
    for k in EXPECTED_FLAGS:
        if k not in flags:
            flags[k] = False  # conservative default
    return flags


def verify_zms_self_test(zms_root: Path) -> bool:
    """Run the ZMS skill's self-test; True if PASSED."""
    test = zms_root / "scripts" / "zms_self_test.py"
    if not test.exists():
        print(f"WARNING: ZMS self-test script not at {test}", file=sys.stderr)
        return True  # allow proceeding without self-test (degraded mode)
    result = subprocess.run(
        ["python3", str(test)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"FATAL: ZMS self-test FAILED. Output:\n{result.stdout}\n"
              f"stderr:\n{result.stderr}", file=sys.stderr)
        return False
    # Confirm "PASSED" appears in stdout
    if "PASSED" not in result.stdout:
        print(f"WARNING: ZMS self-test exit 0 but no PASSED marker:\n{result.stdout}",
              file=sys.stderr)
    return True


def invoke_zms_loader(zms_root: Path, flags: dict, run_id: str,
                      output_dir: Path) -> dict:
    """Invoke the ZMS skill's loader via subprocess.

    Passes {applicability, run_id} as JSON via stdin (ZMS loader's preferred mode).
    Captures the digest JSON from stdout. Returns the digest dict.
    """
    loader = zms_root / "scripts" / "zms_load.py"
    payload = json.dumps({"applicability": flags, "run_id": run_id})

    result = subprocess.run(
        ["python3", str(loader), "--stdin", "--output-dir", str(output_dir)],
        input=payload, capture_output=True, text=True
    )

    if result.returncode != 0:
        print(f"FATAL: ZMS loader exit {result.returncode}", file=sys.stderr)
        print(f"stderr: {result.stderr}", file=sys.stderr)
        sys.exit(4)

    try:
        digest = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"FATAL: ZMS loader output not JSON: {e}\nstdout: {result.stdout[:500]}",
              file=sys.stderr)
        sys.exit(4)

    if digest.get("status") != "ok":
        print(f"FATAL: ZMS digest status not ok: {digest}", file=sys.stderr)
        sys.exit(4)

    return digest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Section B: load ZMS calibration content"
    )
    parser.add_argument("--intake-output",
                        help="Path to section-a-output.json")
    parser.add_argument("--run-id",
                        help="Run ID (e.g., W2-2026-06-03-xxxxxxxx)")
    parser.add_argument("--output-dir", required=True,
                        help="Where to write zms-calibration-content.json")
    parser.add_argument("--zms-skill-root", default=None,
                        help="Override ZMS skill location (default: auto-detect)")
    parser.add_argument("--stdin", action="store_true",
                        help="Read {intake_output_path, run_id, zms_skill_root} from stdin")
    parser.add_argument("--skip-self-test", action="store_true",
                        help="Skip the ZMS self-test (not recommended for production)")
    args = parser.parse_args()

    if args.stdin:
        try:
            payload = json.load(sys.stdin)
        except json.JSONDecodeError as e:
            print(f"ERROR: stdin not valid JSON: {e}", file=sys.stderr)
            return 2
        intake_path = payload.get("intake_output_path", "")
        run_id = payload.get("run_id", "")
        zms_root_override = payload.get("zms_skill_root", args.zms_skill_root)
    else:
        if not args.intake_output or not args.run_id:
            print("ERROR: must provide --intake-output and --run-id (or use --stdin)",
                  file=sys.stderr)
            return 2
        intake_path = args.intake_output
        run_id = args.run_id
        zms_root_override = args.zms_skill_root

    # Load intake
    if not Path(intake_path).exists():
        print(f"ERROR: section-a-output.json not at {intake_path}", file=sys.stderr)
        return 2
    try:
        intake = json.loads(Path(intake_path).read_text())
    except json.JSONDecodeError as e:
        print(f"ERROR: section-a-output.json malformed: {e}", file=sys.stderr)
        return 2

    # Resolve ZMS skill root
    try:
        zms_root = find_zms_skill_root(zms_root_override)
    except FileNotFoundError as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 3
    print(f"[zms_load] using ZMS skill at: {zms_root}", file=sys.stderr)

    # Self-test
    if not args.skip_self_test:
        if not verify_zms_self_test(zms_root):
            return 3

    # Derive applicability
    flags = derive_applicability(intake)
    fired = sorted([k for k, v in flags.items() if v])
    print(f"[zms_load] applicability flags fired ({len(fired)}/{len(flags)}): "
          f"{fired}", file=sys.stderr)

    # Output dir
    out_dir = Path(args.output_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"FATAL: cannot create {out_dir}: {e}", file=sys.stderr)
        return 5

    # Invoke ZMS loader
    digest = invoke_zms_loader(zms_root, flags, run_id, out_dir)

    # ---- v3.7.2: slice calibration content by dimension group ----
    # Each Section D sub-batch loads ONLY its dimension group's criteria
    # (4a/4c -> dims 1-3, 4b/4d -> dims 4-7), roughly halving the per-sub-batch
    # calibration payload. Slices are derived from zms-22-mapping.json, whose
    # sub-criterion keys encode the dimension as their first character.
    slice_info = {}
    try:
        content_path = out_dir / "zms-calibration-content.json"
        mapping_path = zms_root / "data" / "zms-22-mapping.json"
        content = json.loads(content_path.read_text())
        mapping = json.loads(mapping_path.read_text())["mapping"]
        crit_key = "applicable_criteria" if "applicable_criteria" in content else "criteria"
        crit_by_id = {c["id"]: c for c in content[crit_key]}
        groups = {"dims-1-3": "123", "dims-4-7": "4567"}
        for gname, dims in groups.items():
            ids = set()
            for sub, cids in mapping.items():
                if sub and sub[0] in dims:
                    ids.update(cids)
            sliced = [crit_by_id[i] for i in sorted(ids) if i in crit_by_id]
            out = dict(content)
            out[crit_key] = sliced
            out["dimension_group"] = gname
            out["slice_of"] = str(content_path.name)
            spath = out_dir / f"zms-calibration-{gname}.json"
            spath.write_text(json.dumps(out, indent=2, ensure_ascii=False))
            slice_info[gname] = {"path": str(spath), "criteria_count": len(sliced)}
        print(f"[zms_load] dim-group slices written: "
              f"1-3={slice_info['dims-1-3']['criteria_count']} criteria, "
              f"4-7={slice_info['dims-4-7']['criteria_count']} criteria", file=sys.stderr)
    except Exception as e:  # slicing is an optimisation; never fail the load for it
        print(f"[zms_load] WARNING: dim-group slicing skipped: {e}", file=sys.stderr)
        slice_info = {"error": str(e)}

    # Wrap digest with evaluate-sdd-side metadata
    section_b_output = {
        "section": "B",
        "status": "ok",
        "run_id": run_id,
        "zms_skill_root": str(zms_root),
        "applicability_flags_derived": flags,
        "calibration_slices": slice_info,
        "zms_digest": digest,
    }

    section_b_path = out_dir / "section-b-output.json"
    section_b_path.write_text(json.dumps(section_b_output, indent=2, ensure_ascii=False))
    print(json.dumps(section_b_output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
