#!/usr/bin/env python3
"""judge_accumulate.py — dual-judge scorecard persistence + lane aggregation
(v4.7). The dual-judge sibling of pass_accumulate.py, which stays untouched
and frozen for the EVAL_PROTOCOL=five-pass regression path (PRD D6, TRD §4).

WHAT THIS MODULE OWNS
---------------------
- Persisting each judge's scorecard VERBATIM to
      <run>/scorecards/<lane>_<group>_<judge>.json
  at consensus start, BEFORE any diff runs (Backend Schema §5): the audit
  trail of what each judge actually said is independent of packet retention
  and of everything the consensus stage later does with it.
- Loading scorecard pairs for the consensus engine.
- aggregate(lane, run_dir): collapsing the lane's two consensus records
  (consensus/<lane>_<group>.json, written by the orchestrator after
  server/consensus.py merges) into the bundle-facing shape:
  judge_runs_by_dimension, consensus per-dim means/bands, three-key
  sub-score entries, consensus verdicts + provenance + judge entries +
  ruling citations, and the merged dissent list.

WHAT THIS MODULE DOES NOT OWN
-----------------------------
Statistics. Agreement statistics are computed exactly once, in
server/consensus.py (stats()/merge_lane_stats(); TR-21 single-source rule).
aggregate() returns the stored per-group stats untouched under "group_stats";
the caller merges them via consensus.merge_lane_stats.

All deterministic. stdlib + contracts only. `--selftest` runs with no model.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contracts

VALID_GROUPS = ("1-3", "4-7")
GROUP_DIMS = {"1-3": ("1", "2", "3"), "4-7": ("4", "5", "6", "7")}


# ------------------------------------------------------------------- paths
def scorecard_path(run_dir: Path, lane: str, group: str, judge: str) -> Path:
    return Path(run_dir) / "scorecards" / f"{lane}_{group}_{judge}.json"


def consensus_path(run_dir: Path, lane: str, group: str) -> Path:
    return Path(run_dir) / "consensus" / f"{lane}_{group}.json"


# ----------------------------------------------------------------- persist
def persist_scorecard(run_dir: Path, lane: str, group: str, judge: str,
                      scorecard: dict, force: bool = False) -> Path:
    """Write one judge's scorecard verbatim, write-once (independence guard:
    a scorecard must never be silently replaced after consensus has seen it)."""
    if lane not in ("A", "B"):
        raise SystemExit(f"ERROR: lane must be A or B, got {lane!r}")
    if group not in VALID_GROUPS:
        raise SystemExit(f"ERROR: dim-group must be one of {VALID_GROUPS}, got {group!r}")
    if judge not in contracts.JUDGES:
        raise SystemExit(f"ERROR: judge must be one of {contracts.JUDGES}, got {judge!r}")
    out = scorecard_path(run_dir, lane, group, judge)
    if out.exists() and not force:
        return out  # idempotent: the first write stands
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(scorecard, indent=2, sort_keys=True), encoding="utf-8")
    return out


def load_scorecards(run_dir: Path, lane: str, group: str) -> dict:
    """Load the pair {judge: scorecard} for one (lane, group); HALT on gaps —
    consensus over half a panel would be silent single-judge scoring, which
    is exactly the provenance lie TR-8 forbids."""
    cards, missing = {}, []
    for judge in contracts.JUDGES:
        p = scorecard_path(run_dir, lane, group, judge)
        if not p.exists():
            missing.append(p.name)
            continue
        cards[judge] = json.loads(p.read_text(encoding="utf-8"))
    if missing:
        raise SystemExit(
            f"ERROR: missing scorecards for lane {lane} dims {group}: {missing}. "
            "Both judges must have scored from their byte-identical packets "
            "before consensus. (A clean halt beats a single-judge merge.)")
    return cards


def load_consensus(run_dir: Path, lane: str, group: str) -> dict:
    p = consensus_path(run_dir, lane, group)
    if not p.exists():
        raise SystemExit(
            f"ERROR: missing consensus record {p.name} for lane {lane}. "
            "Run the consensus batch before aggregation.")
    return json.loads(p.read_text(encoding="utf-8"))


# --------------------------------------------------------------- aggregate
def aggregate(lane: str, run_dir: Path, integration_heavy: bool = False) -> dict:
    """Collapse the lane's two consensus records into the bundle-facing
    aggregate (the v4.7 analogue of pass_accumulate.aggregate)."""
    records = {g: load_consensus(run_dir, lane, g) for g in VALID_GROUPS}

    judge_runs = {j: {} for j in contracts.JUDGES}
    judge_runs["consensus"] = {}
    per_dim_mean, per_dim_band, per_dim_agreement = {}, {}, {}
    sub_scores, items = {}, {}
    dissents, group_stats = [], []

    for g in VALID_GROUPS:
        rec = records[g]
        for d in GROUP_DIMS[g]:
            ds = (rec.get("dim_scores") or {}).get(d) or {}
            for j in contracts.JUDGES:
                judge_runs[j][d] = ds.get(j)
            judge_runs["consensus"][d] = ds.get("consensus")
            mean = ds.get("consensus")
            per_dim_mean[d] = mean
            mx = contracts.dim_max(int(d), integration_heavy)
            per_dim_band[d] = (contracts.band_for_pct(100.0 * mean / mx)
                               if isinstance(mean, (int, float)) and mx else "")
        for d, subs in (rec.get("sub_scores") or {}).items():
            sub_scores[d] = subs
        items.update(rec.get("items") or {})
        dissents.extend(rec.get("dissents") or [])
        st = rec.get("stats") or {}
        group_stats.append(st)
        for d, v in (st.get("score_concordance_per_dim") or {}).items():
            per_dim_agreement[d] = v

    consensus_verdicts = {cid: it.get("consensus") for cid, it in items.items()}
    consensus_provenance = {cid: it.get("provenance") for cid, it in items.items()}
    judge_entries = {cid: it.get("judge_entries") for cid, it in items.items()
                     if it.get("provenance") != "agreed" and it.get("judge_entries")}
    ruling_citations = {cid: it.get("ruling_citation") for cid, it in items.items()
                        if it.get("ruling_citation")}
    ruling_rationales = {cid: it.get("ruling_rationale") for cid, it in items.items()
                         if it.get("ruling_rationale")}

    return {
        "lane": lane,
        "protocol": "dual-judge",
        "judges": list(contracts.JUDGES),
        "judge_runs_by_dimension": judge_runs,
        "per_dim_mean": per_dim_mean,
        "per_dim_band": per_dim_band,
        "per_dim_agreement": per_dim_agreement,
        "sub_scores": sub_scores,
        "consensus_verdicts": consensus_verdicts,
        "consensus_provenance": consensus_provenance,
        "judge_entries": judge_entries,
        "ruling_citations": ruling_citations,
        "ruling_rationales": ruling_rationales,
        "dissents": dissents,
        "group_stats": group_stats,
        "note": ("Dual-judge lane aggregate: consensus per-dim values are the "
                 "authoritative means; judge_runs_by_dimension carries both "
                 "judges' post-adjustment totals for the sheet's Judge A / "
                 "Judge B columns and the per-judge lifts. Merge group_stats "
                 "via server consensus.merge_lane_stats (TR-21)."),
    }


# ---------------------------------------------------------------- selftest
def _selftest() -> int:
    import tempfile
    ok = True
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        ja, jb = contracts.JUDGES
        # persist + write-once
        p = persist_scorecard(td, "A", "1-3", ja, {"dim_scores": {"1": 12.0}})
        persist_scorecard(td, "A", "1-3", ja, {"dim_scores": {"1": 1.0}})  # ignored
        if json.loads(p.read_text())["dim_scores"]["1"] != 12.0:
            print("  FAIL: write-once violated"); ok = False
        else:
            print("  PASS: scorecard write-once")
        try:
            load_scorecards(td, "A", "1-3"); print("  FAIL: missing pair not caught"); ok = False
        except SystemExit:
            print("  PASS: missing scorecard HALTs")
        # aggregate over synthetic consensus records
        for g, dims in GROUP_DIMS.items():
            rec = {"lane": "A", "dim_group": g,
                   "dim_scores": {d: {ja: 10.0, jb: 12.0, "consensus": 11.0} for d in dims},
                   "sub_scores": {d: {"k": {ja: 3.0, jb: 4.0, "consensus": 3.5,
                                            "provenance": "agreed"}} for d in dims},
                   "items": {f"{d}A.x": {"provenance": "agreed",
                                         "consensus": {"verdict": "Present"},
                                         "judge_entries": None,
                                         "ruling_citation": None,
                                         "ruling_rationale": None} for d in dims},
                   "dissents": [],
                   "stats": {"score_concordance_per_dim": {d: 0.9 for d in dims},
                             "non_na_criteria": len(dims)}}
            cp = consensus_path(td, "A", g)
            cp.parent.mkdir(parents=True, exist_ok=True)
            cp.write_text(json.dumps(rec))
        agg = aggregate("A", td)
        if agg["per_dim_mean"] != {str(d): 11.0 for d in range(1, 8)}:
            print(f"  FAIL: per_dim_mean {agg['per_dim_mean']}"); ok = False
        else:
            print("  PASS: consensus means aggregated across both groups")
        if agg["judge_runs_by_dimension"][ja]["4"] != 10.0:
            print("  FAIL: judge runs missing"); ok = False
        else:
            print("  PASS: judge_runs_by_dimension carries both judges + consensus")
        if len(agg["group_stats"]) != 2:
            print("  FAIL: group_stats not returned"); ok = False
        else:
            print("  PASS: group stats passed through untouched (TR-21)")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Persist/aggregate dual-judge scorecards (v4.7).")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=False)
    a = sub.add_parser("aggregate", help="collapse a lane's consensus records")
    a.add_argument("--lane", required=True, choices=["A", "B"])
    a.add_argument("--output-dir", required=True, type=Path)
    a.add_argument("--integration-heavy", action="store_true")
    a.add_argument("--output", type=Path)
    args = ap.parse_args()

    if args.selftest:
        rc = _selftest()
        print("JUDGE-ACCUMULATE SELFTEST:", "PASS" if rc == 0 else "FAIL")
        return rc
    if args.cmd == "aggregate":
        agg = aggregate(args.lane, args.output_dir, args.integration_heavy)
        text = json.dumps(agg, indent=2, sort_keys=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8")
        print(text)
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
