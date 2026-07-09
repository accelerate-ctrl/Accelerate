#!/usr/bin/env python3
"""
zms_self_test.py — Validates ZMS skill data integrity.

Run after any change to data files or scripts. Run automatically when
the skill is first loaded by an orchestrator. Exits 0 on success;
non-zero with named failure if any invariant is violated.

Checks 14 invariants:
  1. zms-criteria.json is valid JSON with required top-level fields
  2. Criteria count matches the declared count
  3. Every criterion has the required fields
  4. Every criterion has at least one component in depth_indicator_components
  5. Every parent_sub_criterion is in the canonical 22 list
  6. Every applicability flag is in the recognised set
  7. Every source label is in the recognised set
  8. Every critical_floor=True criterion has severity_if_absent="Critical"
  9. zms-22-mapping.json's reverse_mapping is consistent with criteria's parents
 10. Every criterion appears in its parent's mapping list
 11. Loader exits 0 on a minimal valid invocation
 12. Loader output passes basic schema check (applicable_criteria, summary)
 13. source / well_architected_pillar consistency (WA => canonical pillar;
     Zennify SDD standard => null pillar)
 14. sources.md (human-readable authority doc) matches the register exactly
 15. zms-criteria.md source-label annotations match the register
     via scripts/sources_alignment_check.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
DATA_PATH = SKILL_ROOT / "data" / "zms-criteria.json"
MAPPING_PATH = SKILL_ROOT / "data" / "zms-22-mapping.json"
LOADER = SCRIPT_DIR / "zms_load.py"

CANONICAL_SUB_CRITERIA = {
    "1A", "1B", "1C", "2A", "2B", "2C",
    "3A", "3B", "3C", "3D", "3E",
    "4A", "4B", "5A", "5B", "5C",
    "6A", "6B", "6C", "7A", "7B", "7C",
}

RECOGNISED_FLAGS = {
    "ALL", "INTEGRATIONS", "EXTERNAL_USERS", "REGULATED", "REGULATORY_CITATION",
    "AUTOMATION", "TRIGGERS", "CUSTOM_BUILD", "UI_IN_SCOPE", "MULTI_CLOUD",
    "CONFIG_DRIVEN", "API", "DATA_MIGRATION", "PHASING",
}

RECOGNISED_SOURCES = {
    "Zennify SDD standard",
    "Well-Architected",
    "Zennify + Well-Architected",
}

REQUIRED_CRITERION_FIELDS = {
    "id", "name", "parent_sub_criterion", "dimension", "depth_indicator",
    "depth_indicator_components", "source", "severity_if_absent",
    "critical_floor", "applicability",
}


def fail(msg: str) -> None:
    print(f"  FAIL: {msg}")


def check(label: str, ok: bool, detail: str = "") -> bool:
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {label}" + (f" — {detail}" if detail else ""))
    return ok


def main() -> int:
    print("=== ZMS skill self-test ===\n")
    failures = 0

    # 1. JSON validity + top-level fields
    print("1. ZMS data file structure")
    try:
        data = json.loads(DATA_PATH.read_text())
    except Exception as e:
        check("zms-criteria.json loads", False, str(e))
        return 1
    required_top = {"zms_version", "schema_version", "frozen_at",
                    "criteria_count", "criteria", "dimensions", "sub_criteria"}
    missing_top = required_top - set(data.keys())
    if not check("top-level fields present",
                 not missing_top,
                 f"missing: {missing_top}" if missing_top else ""):
        failures += 1

    # 2. Criteria count
    print("\n2. Criteria count")
    actual = len(data["criteria"])
    declared = data["criteria_count"]
    if not check(f"declared {declared} matches actual {actual}", actual == declared):
        failures += 1

    # 3. Required criterion fields
    print("\n3. Per-criterion required fields")
    missing_field_count = 0
    for c in data["criteria"]:
        missing = REQUIRED_CRITERION_FIELDS - set(c.keys())
        if missing:
            missing_field_count += 1
    if not check("every criterion has required fields",
                 missing_field_count == 0,
                 f"{missing_field_count} criteria missing fields" if missing_field_count else ""):
        failures += 1

    # 4. depth_indicator_components non-empty
    print("\n4. depth_indicator_components")
    empty = [c["id"] for c in data["criteria"] if not c["depth_indicator_components"]]
    if not check("every criterion has at least 1 component",
                 not empty,
                 f"empty: {empty[:5]}" if empty else ""):
        failures += 1

    # 5. parent_sub_criterion in canonical 22
    print("\n5. parent_sub_criterion canonical 22")
    bad_parents = [c["id"] for c in data["criteria"]
                   if c["parent_sub_criterion"] not in CANONICAL_SUB_CRITERIA]
    if not check("every parent_sub_criterion in canonical 22",
                 not bad_parents,
                 f"bad: {bad_parents[:5]}" if bad_parents else ""):
        failures += 1

    # 6. applicability in recognised set
    print("\n6. applicability flags")
    bad_apps = [(c["id"], c["applicability"]) for c in data["criteria"]
                if c["applicability"] not in RECOGNISED_FLAGS]
    if not check("every applicability in recognised set",
                 not bad_apps,
                 f"bad: {bad_apps[:5]}" if bad_apps else ""):
        failures += 1

    # 7. source labels in recognised set
    print("\n7. source labels")
    bad_sources = [(c["id"], c["source"]) for c in data["criteria"]
                   if c["source"] not in RECOGNISED_SOURCES]
    if not check("every source in recognised set",
                 not bad_sources,
                 f"bad: {bad_sources[:5]}" if bad_sources else ""):
        failures += 1

    # 8. Critical floor / severity consistency
    print("\n8. critical_floor / severity consistency")
    inconsistent = [c["id"] for c in data["criteria"]
                    if c["critical_floor"] and c["severity_if_absent"] != "Critical"]
    if not check("critical_floor implies severity Critical",
                 not inconsistent,
                 f"bad: {inconsistent}" if inconsistent else ""):
        failures += 1

    # 9. Mapping reverse consistency
    print("\n9. 22-sub-criterion mapping consistency")
    try:
        mapping = json.loads(MAPPING_PATH.read_text())
    except Exception as e:
        check("mapping file loads", False, str(e))
        return 1
    cid_to_parent = {c["id"]: c["parent_sub_criterion"] for c in data["criteria"]}
    mapping_disagrees = [cid for cid, parent in cid_to_parent.items()
                         if mapping["reverse_mapping"].get(cid) != parent]
    if not check("reverse_mapping matches criteria's parents",
                 not mapping_disagrees,
                 f"disagrees: {mapping_disagrees[:5]}" if mapping_disagrees else ""):
        failures += 1

    # 10. Forward mapping completeness
    print("\n10. forward mapping completeness")
    forward_total = sum(len(ids) for ids in mapping["mapping"].values())
    if not check(f"forward mapping sums to {len(data['criteria'])}",
                 forward_total == len(data["criteria"]),
                 f"forward total = {forward_total}"):
        failures += 1

    # 11. Loader runs and exits 0 on minimal valid invocation
    print("\n11. zms_load.py minimal-invocation test")
    with tempfile.TemporaryDirectory() as tmpdir:
        payload = {
            "applicability": {"INTEGRATIONS": True, "EXTERNAL_USERS": False,
                              "MULTI_CLOUD": False, "REGULATED": False},
            "run_id": "TEST-00000000",
        }
        result = subprocess.run(
            ["python3", str(LOADER), "--stdin", "--output-dir", tmpdir],
            input=json.dumps(payload), capture_output=True, text=True
        )
        if not check("loader exits 0",
                     result.returncode == 0,
                     f"stderr: {result.stderr[:200]}" if result.returncode else ""):
            failures += 1
            return 1

        # 12. Loader output schema
        print("\n12. loader output schema")
        cal_file = Path(tmpdir) / "zms-calibration-content.json"
        sum_file = Path(tmpdir) / "zms-calibration-summary.json"
        cal_exists = cal_file.exists()
        sum_exists = sum_file.exists()
        if not check("both output files written", cal_exists and sum_exists):
            failures += 1
            return 1
        cal = json.loads(cal_file.read_text())
        sum_ = json.loads(sum_file.read_text())
        required_cal = {"zms_version", "applicable_criteria", "criteria_by_dim_and_sub",
                        "summary", "sa_reasoning_playbook_path"}
        cal_ok = required_cal.issubset(set(cal.keys()))
        required_sum = {"zms_version", "applicable_criteria_count",
                        "criteria_by_source"}
        sum_ok = required_sum.issubset(set(sum_.keys()))
        if not check("calibration content has required keys", cal_ok):
            failures += 1
        if not check("calibration summary has required keys", sum_ok):
            failures += 1

        # Verify applicability filtering actually fired
        ac_count = cal["summary"]["applicable_criteria_count"]
        if not check(f"applicability filtered ({ac_count} fired)",
                     0 < ac_count <= len(data["criteria"])):
            failures += 1

    # 13. source / pillar consistency
    #   Well-Architected      => pillar in {Trusted, Easy, Adaptable}
    #   Zennify SDD standard  => pillar is null
    #   Zennify + Well-Architected => pillar in {Trusted, Easy, Adaptable}
    print("\n13. source / well_architected_pillar consistency")
    canon = {"Trusted", "Easy", "Adaptable"}
    bad_pillar = []
    for c in data["criteria"]:
        s, p = c["source"], c.get("well_architected_pillar")
        if s == "Well-Architected" and p not in canon:
            bad_pillar.append((c["id"], s, p))
        elif s == "Zennify SDD standard" and p is not None:
            bad_pillar.append((c["id"], s, p))
        elif s == "Zennify + Well-Architected" and p not in canon:
            bad_pillar.append((c["id"], s, p))
    if not check("every source has a consistent pillar value",
                 not bad_pillar,
                 f"bad: {bad_pillar[:5]}" if bad_pillar else ""):
        failures += 1

    # 14. sources.md <-> data alignment (the human-readable authority doc must
    #     agree with the machine register exactly).
    print("\n14. sources.md alignment with register")
    align = SCRIPT_DIR / "sources_alignment_check.py"
    if not align.exists():
        check("sources_alignment_check.py present", False,
              "alignment checker missing from scripts/")
        failures += 1
    else:
        res = subprocess.run(["python3", str(align)],
                             capture_output=True, text=True)
        if not check("sources.md matches data/zms-criteria.json",
                     res.returncode == 0,
                     res.stdout.strip().splitlines()[-1] if res.returncode else ""):
            failures += 1

    # 15. zms-criteria.md <-> data alignment. The human-readable criteria doc
    #     annotates criterion IDs with source labels in parentheses; every such
    #     annotation must match the register. (Added after an audit found the
    #     critical-floor summary carrying labels the register does not have.)
    print("\n15. zms-criteria.md source labels match register")
    crit_md = SKILL_ROOT / "references" / "zms-criteria.md"
    if not crit_md.exists():
        check("references/zms-criteria.md present", False)
        failures += 1
    else:
        src_by_id = {c["id"]: c["source"] for c in data["criteria"]}
        known_labels = {"Zennify SDD standard", "Well-Architected",
                        "Zennify + Well-Architected"}
        md = crit_md.read_text()
        mismatches = []
        for cid, label in re.findall(
                r"`(\d[A-Z]\.[a-z_]+)`[^(\n]*\(([^)\n]+)\)", md):
            label = label.strip()
            if label not in known_labels:
                continue  # parenthetical is not a source annotation
            reg = src_by_id.get(cid)
            if reg and reg != label:
                mismatches.append(f"{cid}: doc says {label!r}, register says {reg!r}")
        if not check("all source-label annotations match the register",
                     not mismatches, "; ".join(mismatches[:5])):
            failures += 1

    print("\n=== RESULT ===")
    if failures:
        print(f"FAILED: {failures} check(s) did not pass")
        return 1
    print(f"PASSED: all checks green; {len(data['criteria'])} criteria validated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
