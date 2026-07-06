#!/usr/bin/env python3
"""
release_awareness_check.py — COMPATIBILITY SHIM (v3.8.0).

The release-currency engine moved to release_crosswalk.py (two-call live path:
extract -> orchestrator web_search -> resolve). This shim preserves the old
single-call CLI for any caller that still invokes the v3.7 name. It runs the
extract step then a register-only resolve (no live evidence), which is exactly
the offline/no-evidence fallback. For the live path, call release_crosswalk.py
directly.

Old CLI:
    python3 release_awareness_check.py --sdd-path <sdd> --lane A \
        --run-id <id> --output-dir <run>
Emits <run>/release-awareness-A.json + digest to stdout.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import release_crosswalk as rc
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import release_crosswalk as rc

# Re-export helpers some callers/tests import by the old name.
SEVERITY_DEDUCTION = {"Critical": -5, "Major": -3, "Minor": -1, None: 0}
is_salesforce_url = rc.is_salesforce_url
MECHANISM_PATTERNS = rc.MECHANISM_PATTERNS


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Section C.5 (compat shim — register-only resolve; "
                    "use release_crosswalk.py for the live path)")
    parser.add_argument("--sdd-path", required=True)
    parser.add_argument("--lane", required=True, choices=["A", "B", "a", "b"])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--as-of", default=None)
    args = parser.parse_args()

    lane = args.lane.upper()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    sdd_path = Path(args.sdd_path)
    if not sdd_path.exists():
        print(f"ERROR: SDD not at {sdd_path}", file=sys.stderr)
        return 2
    try:
        text = rc.read_sdd_text(sdd_path)
    except (ValueError, OSError) as e:
        print(f"ERROR: cannot read SDD: {e}", file=sys.stderr)
        return 2

    as_of = args.as_of or datetime.now(timezone.utc).date().isoformat()

    queries_doc = rc.do_extract(text, lane, args.run_id)
    queries_doc["sdd_path"] = str(sdd_path)
    # Back-compat shim stays lenient: a broken register degrades rather than raising,
    # but the status is still surfaced so the silent-zero gap is closed here too.
    try:
        register, register_status = rc.load_register_status()
    except rc.RegisterLoadError as e:
        register, register_status = {}, "error"
        print(f"WARNING: register load failed ({e}); proceeding register-empty.", file=sys.stderr)
    findings, live_used = rc.do_resolve(queries_doc, {}, register, lane, args.run_id, as_of)
    output = rc.assemble_output(findings, lane, args.run_id, str(sdd_path), live_used,
                                register_status=register_status)

    out_path = out_dir / f"release-awareness-{lane}.json"
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(json.dumps({
        "status": "ok", "section": "C.5", "compat_shim": True,
        "live_path_used": live_used, "lane": lane,
        "findings_count": len(findings),
        "by_status": output["summary"]["by_status"],
        "rr_deductions_capped_total": output["summary"]["rr_deductions_capped_total"],
        "findings_path": str(out_path),
        "note": "Register-only resolve via compat shim. For live verification, "
                "use release_crosswalk.py extract|resolve.",
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
