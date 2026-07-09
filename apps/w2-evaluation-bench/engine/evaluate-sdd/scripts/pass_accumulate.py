#!/usr/bin/env python3
"""pass_accumulate.py — genuinely independent five-pass scoring (v4.6).

WHY THIS EXISTS
---------------
Before v4.5 the "five passes" were produced inside a SINGLE turn, so the model
saw all five at once: they were correlated by construction and their standard
deviation was theatre, not a reliability signal. v4.5 makes the five passes
REAL: each pass is its own turn, scored COLD, and written to its own file. No
turn ever holds a five-element array — mid-stream the passes exist only as
separate files on disk. The mean/stddev computed by `aggregate` is therefore a
genuine measure of pass-to-pass stability.

TURN PROTOCOL (Section D, per sub-batch)
----------------------------------------
A sub-batch is one lane x one dim-group (e.g. lane A, dims 1-3). It is scored in
FIVE sequential turns. In each turn the model reads the SDD + calibration cold,
scores that dim-group for THAT pass only, and ends the turn with:

    pass_accumulate.py record --lane A --dim-group 1-3 --pass 1 \
        --scores <pass-scores.json> --output-dir <run>

writing exactly one file:

    <run>/passes/A_1-3_pass1.json   (only this pass's numbers; never an array)

After all five passes of a sub-batch (and after both dim-groups of a lane), the
aggregator collapses the per-pass files into the per-dimension five-pass arrays,
means, stddevs, and variance flags the scoring bundle needs:

    pass_accumulate.py aggregate --lane A --output-dir <run> \
        --output <run>/lane-A-pass-aggregate.json

INPUT to `record` (--scores <file.json>), the single pass's cold scoring:
    {
      "dim_scores": {"1": 12.9, "2": 14.0, "3": 15.8},   # net per-dimension this pass
      "sub_scores": {"1A": 4, "1B": 4, "1C": 5, "2A": 5, ...},
      "verdicts":   {"1A.field": "Partial", "1A.object": "Present", ...}  # optional
    }
`dim_scores` are NET (Dim-3 deductions and the Dim-4 floor cap already applied by
the model for that pass); the aggregator never re-applies them.

All deterministic. stdlib only. `--selftest` runs the aggregation math with no model.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contracts

VALID_GROUPS = ("1-3", "4-7")
GROUP_DIMS = {"1-3": ("1", "2", "3"), "4-7": ("4", "5", "6", "7")}
N_PASSES = 5
VALID_VERDICTS = {"Present", "Partial", "Absent", "NA"}


# ----------------------------------------------------------------------- record
def record(lane: str, dim_group: str, pass_no: int, scores: dict,
           output_dir: Path, force: bool = False) -> dict:
    if lane not in ("A", "B"):
        raise SystemExit(f"ERROR: lane must be A or B, got {lane!r}")
    if dim_group not in VALID_GROUPS:
        raise SystemExit(f"ERROR: dim-group must be one of {VALID_GROUPS}, got {dim_group!r}")
    if not (1 <= pass_no <= N_PASSES):
        raise SystemExit(f"ERROR: pass must be 1..{N_PASSES}, got {pass_no}")

    dim_scores = scores.get("dim_scores") or {}
    sub_scores = scores.get("sub_scores") or {}
    verdicts = scores.get("verdicts") or {}
    expected_dims = set(GROUP_DIMS[dim_group])
    got_dims = set(str(k) for k in dim_scores)
    if got_dims != expected_dims:
        raise SystemExit(
            f"ERROR: dim_scores keys {sorted(got_dims)} != expected {sorted(expected_dims)} "
            f"for dim-group {dim_group}. Each pass must score exactly its dim-group.")
    for d, v in dim_scores.items():
        if not isinstance(v, (int, float)):
            raise SystemExit(f"ERROR: dim_scores[{d!r}] is not numeric: {v!r}")
    for s, v in sub_scores.items():
        if not isinstance(v, (int, float)):
            raise SystemExit(f"ERROR: sub_scores[{s!r}] is not numeric: {v!r}")
    for c, vd in verdicts.items():
        if vd not in VALID_VERDICTS:
            raise SystemExit(f"ERROR: verdicts[{c!r}] = {vd!r} not in {sorted(VALID_VERDICTS)}")

    rec = {
        "lane": lane,
        "dim_group": dim_group,
        "pass": pass_no,
        "scored_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dim_scores": {str(k): float(v) for k, v in dim_scores.items()},
        "sub_scores": {str(k): float(v) for k, v in sub_scores.items()},
        "verdicts": {str(k): v for k, v in verdicts.items()},
    }
    passes_dir = Path(output_dir) / "passes"
    passes_dir.mkdir(parents=True, exist_ok=True)
    out = passes_dir / f"{lane}_{dim_group}_pass{pass_no}.json"
    if out.exists() and not force:
        raise SystemExit(
            f"ERROR: {out} already exists. Each pass is written once (independence "
            f"guard). Pass --force only to deliberately re-record a contaminated pass.")
    out.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    return {"status": "recorded", "file": str(out), "lane": lane,
            "dim_group": dim_group, "pass": pass_no,
            "dims_recorded": sorted(rec["dim_scores"])}


# -------------------------------------------------------------------- aggregate
def _modal(values: list[str]):
    """Most-common verdict; ties resolve to the more conservative (Absent>Partial>Present>NA)."""
    if not values:
        return None
    order = {"Absent": 0, "Partial": 1, "Present": 2, "NA": 3}
    counts: dict[str, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    top = max(counts.values())
    tied = [v for v, c in counts.items() if c == top]
    return sorted(tied, key=lambda v: order.get(v, 9))[0]


def aggregate(lane: str, output_dir: Path) -> dict:
    passes_dir = Path(output_dir) / "passes"
    if not passes_dir.exists():
        raise SystemExit(f"ERROR: no passes/ directory under {output_dir}")

    # Load all five passes of both dim-groups for this lane; HALT on any gap.
    loaded: dict[str, dict[int, dict]] = {g: {} for g in VALID_GROUPS}
    missing = []
    for g in VALID_GROUPS:
        for n in range(1, N_PASSES + 1):
            f = passes_dir / f"{lane}_{g}_pass{n}.json"
            if not f.exists():
                missing.append(f.name)
                continue
            loaded[g][n] = json.loads(f.read_text())
    if missing:
        raise SystemExit(
            "ERROR: missing pass files for lane "
            f"{lane}: {missing}. All {N_PASSES} passes of both dim-groups (1-3 and "
            "4-7) must be recorded before aggregation. (A clean halt beats a "
            "partial bundle.)")

    # v4.6 — turn-protocol plausibility check. The five passes MUST each be
    # scored in their own cold turn (SKILL.md hard rule 2; section-d-core
    # five-run discipline). Scripts cannot see turns, but every pass file
    # carries its scored_at stamp: five genuinely independent turns — each a
    # cold re-read of the SDD + calibration slice — cannot plausibly all land
    # inside a tight window. If they do, the stddev is single-turn theatre.
    # Surfaced only (wall-clock is a signal, not proof): the flag travels in
    # the aggregate output and digest so the variance record and the D.5
    # checkpoint can show it.
    pass_timing_flags: list[str] = []
    for g in VALID_GROUPS:
        stamps = []
        for n in range(1, N_PASSES + 1):
            ts = loaded[g][n].get("scored_at")
            if ts:
                try:
                    stamps.append(datetime.fromisoformat(ts))
                except ValueError:
                    pass
        if len(stamps) == N_PASSES:
            span = (max(stamps) - min(stamps)).total_seconds()
            if span < 120:
                pass_timing_flags.append(
                    f"SINGLE-TURN-SUSPECT [{lane} dims {g}]: all {N_PASSES} pass files were "
                    f"recorded within {int(span)}s. Five genuinely independent cold "
                    "turns (each re-reading the SDD and calibration slice from "
                    "scratch) are implausible in that window — verify the "
                    "one-pass-per-turn protocol was followed; the pass stddev may "
                    "not be a real stability signal.")

    # Per-dimension five-pass arrays (net scores), in pass order 1..5.
    five_runs: dict[str, list[float]] = {}
    for g in VALID_GROUPS:
        for d in GROUP_DIMS[g]:
            five_runs[d] = [loaded[g][n]["dim_scores"][d] for n in range(1, N_PASSES + 1)]

    per_dim_mean, per_dim_stddev, per_dim_flag, per_dim_band = {}, {}, {}, {}
    for d in (str(i) for i in range(1, 8)):
        arr = five_runs[d]
        mean = round(sum(arr) / len(arr), 1)
        sd = round(statistics.stdev(arr), 2) if len(arr) >= 2 else 0.0
        per_dim_mean[d] = mean
        per_dim_stddev[d] = sd
        per_dim_flag[d] = sd > 1.0
        pct = 100.0 * mean / contracts.dim_max(int(d))
        per_dim_band[d] = contracts.band_for_pct(pct)

    # Per-sub-criterion five-pass arrays (keyed by code, e.g. "3B").
    sub_codes = set()
    for g in VALID_GROUPS:
        for n in range(1, N_PASSES + 1):
            sub_codes.update(loaded[g][n].get("sub_scores", {}))
    sub_score_arrays: dict[str, list] = {}
    for code in sorted(sub_codes):
        g = "1-3" if code[0] in "123" else "4-7"
        arr = []
        for n in range(1, N_PASSES + 1):
            arr.append(loaded[g][n].get("sub_scores", {}).get(code))
        sub_score_arrays[code] = arr

    # Modal verdict per criterion across the five passes (for content_coding).
    crit_verdicts: dict[str, list[str]] = {}
    for g in VALID_GROUPS:
        for n in range(1, N_PASSES + 1):
            for crit, vd in loaded[g][n].get("verdicts", {}).items():
                crit_verdicts.setdefault(crit, []).append(vd)
    modal_verdicts = {c: _modal(v) for c, v in crit_verdicts.items()}
    verdict_unstable = {c: len(set(v)) > 1 for c, v in crit_verdicts.items()}

    # Honest independence check: with REAL independent passes this should show
    # genuine spread. If it is degenerate (near-identical across dims) the passes
    # were not actually independent and the report must say so.
    try:
        from pass_correlation import assess_pass_correlation
        pass_corr = assess_pass_correlation({d: five_runs[d] for d in five_runs})
    except Exception:
        pass_corr = None

    return {
        "lane": lane,
        "n_passes": N_PASSES,
        "aggregated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "five_runs_by_dimension": five_runs,
        "per_dim_mean": per_dim_mean,
        "per_dim_stddev": per_dim_stddev,
        "per_dim_variance_flag": per_dim_flag,
        "per_dim_band": per_dim_band,
        "sub_score_arrays": sub_score_arrays,
        "modal_verdicts": modal_verdicts,
        "verdict_unstable": {c: u for c, u in verdict_unstable.items() if u},
        "pass_correlation": pass_corr,
        "pass_timing_flags": pass_timing_flags,
        "note": ("Five genuinely independent passes (one per turn, each scored "
                 "cold). Means/stddevs are real pass-to-pass stability, not "
                 "single-turn theatre. Merge five_runs_by_dimension, per_dim_*, "
                 "and the sub arrays into the scoring bundle; author content_coding "
                 "anchors using modal_verdicts."),
    }


# --------------------------------------------------------------------- selftest
def _selftest() -> int:
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        # Five independent-ish passes for lane A, both groups.
        g13 = [{"1": 13, "2": 14, "3": 16}, {"1": 12, "2": 14, "3": 15},
               {"1": 13, "2": 13, "3": 16}, {"1": 14, "2": 14, "3": 15},
               {"1": 12, "2": 14, "3": 16}]
        g47 = [{"4": 12, "5": 9, "6": 9, "7": 13}, {"4": 13, "5": 8, "6": 9, "7": 14},
               {"4": 12, "5": 9, "6": 8, "7": 13}, {"4": 13, "5": 9, "6": 9, "7": 13},
               {"4": 12, "5": 8, "6": 9, "7": 14}]
        for n in range(1, 6):
            record("A", "1-3", n, {"dim_scores": g13[n - 1],
                   "sub_scores": {"1A": 4, "3B": 3}, "verdicts": {"3B.audit": "Partial"}}, td)
            record("A", "4-7", n, {"dim_scores": g47[n - 1], "sub_scores": {"4A": 8}}, td)
        agg = aggregate("A", td)
        # check dim-1 mean = mean(13,12,13,14,12)=12.8
        if agg["per_dim_mean"]["1"] != 12.8:
            print(f"  FAIL: dim1 mean {agg['per_dim_mean']['1']} != 12.8"); ok = False
        else:
            print("  PASS: dim1 five-pass mean 12.8 from 5 independent files")
        if len(agg["five_runs_by_dimension"]["1"]) != 5:
            print("  FAIL: dim1 array not length 5"); ok = False
        else:
            print("  PASS: five_runs arrays length 5")
        # missing-pass guard
        (td / "passes" / "A_4-7_pass5.json").unlink()
        try:
            aggregate("A", td); print("  FAIL: missing-pass not caught"); ok = False
        except SystemExit:
            print("  PASS: missing pass HALTs aggregation")
        # double-record guard
        try:
            record("A", "1-3", 1, {"dim_scores": g13[0]}, td); print("  FAIL: overwrite allowed"); ok = False
        except SystemExit:
            print("  PASS: re-recording a pass is refused without --force")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Record/aggregate genuinely independent scoring passes.")
    sub = ap.add_subparsers(dest="cmd", required=False)

    r = sub.add_parser("record", help="write one pass's scores to its own file")
    r.add_argument("--lane", required=True, choices=["A", "B"])
    r.add_argument("--dim-group", required=True, choices=list(VALID_GROUPS))
    r.add_argument("--pass", dest="pass_no", required=True, type=int)
    r.add_argument("--scores", required=True, type=Path, help="this pass's scoring JSON")
    r.add_argument("--output-dir", required=True, type=Path)
    r.add_argument("--force", action="store_true")

    a = sub.add_parser("aggregate", help="collapse the five per-pass files into bundle stats")
    a.add_argument("--lane", required=True, choices=["A", "B"])
    a.add_argument("--output-dir", required=True, type=Path)
    a.add_argument("--output", type=Path)

    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        rc = _selftest()
        print("PASS-ACCUMULATE SELFTEST:", "PASS" if rc == 0 else "FAIL")
        return rc

    if args.cmd == "record":
        scores = json.loads(Path(args.scores).read_text())
        out = record(args.lane, args.dim_group, args.pass_no, scores, args.output_dir, args.force)
        print(json.dumps(out, indent=2))
        return 0
    if args.cmd == "aggregate":
        agg = aggregate(args.lane, args.output_dir)
        text = json.dumps(agg, indent=2)
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(text, encoding="utf-8")
        print(text)
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
