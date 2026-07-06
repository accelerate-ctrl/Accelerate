"""Deterministic pipeline orchestrator.

advance(run_id) executes every batch whose inputs are ready, in order, and
stops when it must wait: on open work packets (model judgment, operator-side
runner) or the mandatory D.5 operator approval. It is safe to call repeatedly
(idempotent per batch: each batch checks its own output artifact first).

Model judgment NEVER happens here. The server holds no model client at all.
"""
from __future__ import annotations
import json
import subprocess
import traceback
from pathlib import Path

from .config import SCRIPTS, ZMS_ROOT, PYTHON, ESCROW_NAME
from . import prompts, packets, bundle_assemble
from .storage import run_dir, load_state, save_state

import contracts
import pass_accumulate
import source_index_build


# ------------------------------------------------------------------ helpers
def _sh(args: list[str], cwd: Path | None = None) -> dict:
    r = subprocess.run(args, capture_output=True, text=True, cwd=cwd)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(str(a) for a in args[:3])}... failed "
                           f"(exit {r.returncode}):\n{r.stderr[-2000:]}\n{r.stdout[-1000:]}")
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"stdout": r.stdout}


def _j(p: Path) -> dict:
    return json.loads(p.read_text())


def _script(name: str) -> str:
    return str(SCRIPTS / name)


# ------------------------------------------------------------------ batches
def batch_intake(rd: Path, st: dict) -> None:
    out = rd / "section-a-output.json"
    if out.exists():
        return
    args = [PYTHON, _script("intake_validate.py"),
            "--input-artefact", str(rd / "inputs" / st["files"]["brd"]),
            "--evaluator-model", st.get("evaluator_model", "claude-code-subscription"),
            "--output-dir", str(rd)]
    if st["mode"] == "A":
        args += ["--candidate-a", str(rd / "inputs" / st["files"]["sdd_1"]),
                 "--candidate-b", str(rd / "inputs" / st["files"]["sdd_2"]),
                 "--zenagent-is", st["zenagent_is"]]
    else:
        args += ["--single-sdd", str(rd / "inputs" / st["files"]["sdd_1"])]
        if st.get("single_sdd_origin"):
            args += ["--single-sdd-origin", st["single_sdd_origin"]]
    digest = _sh(args)
    st["digests"]["intake"] = {k: digest.get(k) for k in
                               ("run_id", "mode", "run_type", "applicability_flags",
                                "integration_count", "run_integration_heavy", "lane_files")}
    # lane_files is the label->path binding (identity-neutral); the escrow stays sealed.
    st["lane_files"] = digest.get("lane_files") or {
        "Output A": str(rd / "inputs" / st["files"]["sdd_1"])}
    st["stage"] = "S1"


def batch_zms(rd: Path, st: dict) -> None:
    if (rd / "zms-calibration-content.json").exists():
        return
    payload = json.dumps({"intake_output_path": str(rd / "section-a-output.json"),
                          "run_id": st["run_id"], "zms_skill_root": str(ZMS_ROOT)})
    r = subprocess.run([PYTHON, _script("zms_load.py"), "--stdin", "--output-dir", str(rd)],
                       input=payload, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"zms_load failed: {r.stderr[-1500:]}")
    d = json.loads(r.stdout)
    st["digests"]["zms"] = {k: d.get(k) for k in
                            ("zms_version", "applicable_criteria_count")}


def _labels(st: dict) -> list[str]:
    return ["Output A", "Output B"] if st["mode"] == "A" else ["Output A"]


def _lane_sdd(st: dict, label: str) -> Path:
    return Path(st["lane_files"][label])


def stage_mapping_packets(rd: Path, st: dict) -> bool:
    """Create components+features packets per lane; True when all results in."""
    need = []
    for label in _labels(st):
        for kind in ("components", "features"):
            pid = f"{kind}:{label}"
            if not packets.result_path(rd, pid).exists():
                need.append((pid, kind, label))
    for pid, kind, label in need:
        if not packets.exists(rd, pid):
            sdd = _lane_sdd(st, label)
            prompt = (prompts.components_prompt(sdd, label) if kind == "components"
                      else prompts.features_prompt(sdd, label))
            packets.create(rd, pid, kind=kind, label=label, prompt=prompt,
                           schema_hint={"components": [], "features": []})
    return not need


def batch_mapping(rd: Path, st: dict) -> None:
    for label in _labels(st):
        suffix = "a" if label.endswith("A") else "b"
        out = rd / f"section-c-output-{suffix}.json"
        if out.exists():
            continue
        comp = packets.result(rd, f"components:{label}")
        comp_path = rd / f"components-{suffix}.json"
        comp_path.write_text(json.dumps(comp))
        d = _sh([PYTHON, _script("content_mapping_classify.py"),
                 "--components-json", str(comp_path), "--blinding-label", label,
                 "--workbook", str(rd / "content-mapping.xlsx"), "--output", str(out)])
        st["digests"].setdefault("mapping", {})[label] = {
            k: d.get(k) for k in ("stub_missing_count_over_8_required", "dim_4_floor_cap")}
    st["stage"] = "S2"


def batch_crosswalk(rd: Path, st: dict) -> bool:
    """extract -> (optional live evidence packet) -> resolve. True when done."""
    done = True
    for label in _labels(st):
        lane = "A" if label.endswith("A") else "B"
        ra = rd / f"release-awareness-{lane}.json"
        if ra.exists():
            continue
        q = rd / f"release-queries-{lane}.json"
        if not q.exists():
            feats = packets.result(rd, f"features:{label}")
            fpath = rd / f"features-{lane}.json"
            fpath.write_text(json.dumps(feats))
            _sh([PYTHON, _script("release_crosswalk.py"), "extract",
                 "--sdd-path", str(_lane_sdd(st, label)), "--lane", lane,
                 "--run-id", st["run_id"], "--output-dir", str(rd),
                 "--features", str(fpath)])
        ev = rd / f"release-evidence-{lane}.json"
        if st.get("live_evidence"):
            pid = f"evidence:{label}"
            if not packets.result_path(rd, pid).exists():
                if not packets.exists(rd, pid):
                    queries = _j(q).get("queries", [])
                    packets.create(rd, pid, kind="evidence", label=label,
                                   prompt=prompts.evidence_prompt(queries, lane),
                                   needs_web=True)
                done = False
                continue
            res = packets.result(rd, pid)
            ev.write_text(json.dumps({"lane": lane, "as_of": res.get("as_of"),
                                      "evidence": res.get("evidence", {})}))
        else:
            ev.write_text(json.dumps({"lane": lane, "evidence": {}}))  # register-only
        d = _sh([PYTHON, _script("release_crosswalk.py"), "resolve",
                 "--queries", str(q), "--evidence", str(ev), "--lane", lane,
                 "--run-id", st["run_id"], "--output-dir", str(rd)])
        st["digests"].setdefault("release", {})[label] = d.get("summary", d)
    return done


def _release_digest(rd: Path, label: str) -> dict:
    lane = "A" if label.endswith("A") else "B"
    p = rd / f"release-awareness-{lane}.json"
    if not p.exists():
        return {}
    d = _j(p)
    return {"by_status": d.get("summary", {}).get("verification_coverage", d.get("summary", {})),
            "rr_capped_total": d.get("summary", {}).get("rr_deductions_capped_total")}


def stage_scoring_packets(rd: Path, st: dict) -> bool:
    """20 pass packets (A/B x 1-3/4-7 x 5) + 2 narrative packets. Mode A only."""
    import pass_plan as pp
    need = False
    for label in _labels(st):
        lane = "A" if label.endswith("A") else "B"
        mapping = st["digests"]["mapping"][label]
        rel = _release_digest(rd, label)
        for group in ("1-3", "4-7"):
            slice_ids = [c["id"] for c in
                         _j(rd / f"zms-calibration-dims-{group}.json")["applicable_criteria"]]
            plans = pp.pass_plan(st["run_id"] + f":{lane}:{group}", slice_ids)
            for n in range(1, 6):
                pid = f"pass:{label}:{group}:{n}"
                if packets.result_path(rd, pid).exists():
                    continue
                need = True
                if not packets.exists(rd, pid):
                    plan = plans[n - 1] if isinstance(plans, list) and len(plans) >= n else {}
                    prompt = prompts.pass_prompt(
                        run_id=st["run_id"], label=label, dim_group=group, pass_n=n,
                        sdd_path=_lane_sdd(st, label),
                        slice_path=rd / f"zms-calibration-dims-{group}.json",
                        playbook_path=Path(_j(rd / "zms-calibration-content.json")
                                           ["sa_reasoning_playbook_path"]),
                        core_ref=SCRIPTS.parent / "references" / "section-d-core.md",
                        dims_ref=SCRIPTS.parent / "references" / f"section-d-dims-{group}.md",
                        plan=plan, mapping_digest=mapping, release_digest=rel)
                    packets.create(rd, pid, kind="pass", label=label, prompt=prompt,
                                   meta={"lane": lane, "dim_group": group, "pass_n": n,
                                         "floor_cap": mapping.get("dim_4_floor_cap"),
                                         "rr_capped_total": _j(rd / f"release-awareness-{lane}.json")
                                                            .get("summary", {})
                                                            .get("rr_deductions_capped_total", 0)
                                                            if (rd / f"release-awareness-{lane}.json").exists() else 0})
    return not need


def batch_record_and_aggregate(rd: Path, st: dict) -> None:
    """Feed pass results through the engine's recorder/aggregator (guards intact)."""
    for label in _labels(st):
        lane = "A" if label.endswith("A") else "B"
        agg_path = rd / f"lane-{lane}-pass-aggregate.json"
        if agg_path.exists():
            continue
        for group in ("1-3", "4-7"):
            for n in range(1, 6):
                res = packets.result(rd, f"pass:{label}:{group}:{n}")
                rec_file = rd / "passes" / f"{lane}_{group}_pass{n}.json"
                if rec_file.exists():
                    continue
                scores = rd / f"_tmp_scores_{lane}_{group}_{n}.json"
                flat_subs = {}
                for dim, subs in (res.get("sub_scores") or {}).items():
                    if isinstance(subs, dict):
                        for j, (skey, val) in enumerate(sorted(
                                subs.items(),
                                key=lambda kv: bundle_assemble.SUB_ORDER.get(kv[0], 99))):
                            code = bundle_assemble.CODE_BY_SUB.get(skey)
                            if code:
                                flat_subs[code] = val
                    else:
                        flat_subs[dim] = subs  # already flat/coded
                scores.write_text(json.dumps({
                    "dim_scores": res["dim_scores"],
                    "sub_scores": flat_subs,
                    "verdicts": {k: v.get("verdict") for k, v in
                                 (res.get("verdicts") or {}).items()},
                }))
                _sh([PYTHON, _script("pass_accumulate.py"), "record", "--lane", lane,
                     "--dim-group", group, "--pass", str(n),
                     "--scores", str(scores), "--output-dir", str(rd)])
                scores.unlink(missing_ok=True)
        agg = pass_accumulate.aggregate(lane, rd)
        agg_path.write_text(json.dumps(agg, indent=2))
        st["digests"].setdefault("aggregate", {})[label] = {
            "per_dim_mean": agg["per_dim_mean"],
            "variance_flags": agg["per_dim_variance_flag"],
            "pass_timing_flags": agg.get("pass_timing_flags", [])}


def stage_narrative_packets(rd: Path, st: dict) -> bool:
    need = False
    for label in _labels(st):
        lane = "A" if label.endswith("A") else "B"
        pid = f"narrative:{label}"
        if packets.result_path(rd, pid).exists():
            continue
        need = True
        if not packets.exists(rd, pid):
            agg = _j(rd / f"lane-{lane}-pass-aggregate.json")
            # Per-dimension digest: up to 3 criteria per dim so every dimension is
            # represented regardless of prompt-size trimming (the narrative needs
            # breadth across dims, not exhaustiveness — the bundle carries that).
            by_dim: dict[str, dict] = {str(d): {} for d in range(1, 8)}
            for group in ("1-3", "4-7"):
                res = packets.result(rd, f"pass:{label}:{group}:1")
                for cid, rec in (res.get("verdicts") or {}).items():
                    dim = cid[0]
                    if len(by_dim.get(dim, {})) >= 3:
                        continue
                    by_dim.setdefault(dim, {})[cid] = {
                        "verdict": agg.get("modal_verdicts", {}).get(cid, rec.get("verdict")),
                        "evidence_anchor": (rec.get("evidence_anchor") or "")[:140],
                        "sdd_ref": rec.get("sdd_ref")}
            coding_digest = {cid: rec for dim in sorted(by_dim) for cid, rec in by_dim[dim].items()}
            prompt = prompts.narrative_prompt(
                label=label,
                aggregate={k: agg[k] for k in ("per_dim_mean", "per_dim_stddev",
                                               "per_dim_variance_flag")},
                coding_digest=coding_digest,
                brd_path=rd / "inputs" / st["files"]["brd"])
            packets.create(rd, pid, kind="narrative", label=label, prompt=prompt)
    return not need


def batch_assemble_bundles(rd: Path, st: dict) -> None:
    calibration = _j(rd / "zms-calibration-content.json")
    run_record = _j(rd / "run-record.json")
    for label in _labels(st):
        lane = "A" if label.endswith("A") else "B"
        suffix = "a" if lane == "A" else "b"
        bpath = rd / f"output-{suffix}-scoring-bundle.json"
        if bpath.exists():
            continue
        agg = _j(rd / f"lane-{lane}-pass-aggregate.json")
        pass_results = [packets.result(rd, f"pass:{label}:{g}:{n}")
                        for g in ("1-3", "4-7") for n in range(1, 6)]
        release = {}
        rp = rd / f"release-awareness-{lane}.json"
        if rp.exists():
            release = _j(rp)
        mapping = _j(rd / f"section-c-output-{suffix}.json")
        bundle = bundle_assemble.assemble(
            run_id=st["run_id"], label=label, aggregate=agg,
            pass_results=pass_results, narrative=packets.result(rd, f"narrative:{label}"),
            calibration=calibration, mapping=mapping, release=release,
            run_record=run_record)
        bundle_assemble.write_bundle(bpath, bundle)
    st["stage"] = "S3"


def build_checkpoint(rd: Path, st: dict) -> dict:
    """The blinded D.5 panel (procedures section D.5)."""
    zs = _j(rd / "zms-calibration-summary.json")
    panel = {"zms": {k: zs.get(k) for k in ("zms_version", "zms_frozen_at",
                                            "applicable_criteria_count", "criteria_by_source")},
             "lanes": {}}
    for label in _labels(st):
        lane = "A" if label.endswith("A") else "B"
        b = _j(rd / f"output-{'a' if lane == 'A' else 'b'}-scoring-bundle.json")
        rel = {}
        rp = rd / f"release-awareness-{lane}.json"
        if rp.exists():
            rel = _j(rp).get("summary", {})
        panel["lanes"][label] = {
            "total": round(sum(b["per_dim_mean"].values()), 1),
            "per_dim_mean": b["per_dim_mean"],
            "variance_flags": [d for d, f in b["per_dim_variance_flag"].items() if f],
            "trust_deductions": sum(1 for x in b["deductions"] if x["id"].startswith("TRUST")),
            "rr_deductions": sum(1 for x in b["deductions"] if x["id"].startswith("RR")),
            "mapping": st["digests"]["mapping"][label],
            "release_summary": {k: rel.get(k) for k in ("findings_total", "by_status",
                                                        "rr_deductions_capped_total")},
            "pass_timing_flags": st["digests"].get("aggregate", {}).get(label, {})
                                  .get("pass_timing_flags", []),
        }
    return panel


def batch_sheets(rd: Path, st: dict) -> None:
    for label in _labels(st):
        suffix = "a" if label.endswith("A") else "b"
        out = rd / f"output-{suffix}-score-sheet.xlsx"
        if out.exists():
            continue
        sdd = _lane_sdd(st, label)
        idx = rd / f"sdd-index-{suffix}.json"
        if not idx.exists():
            _sh([PYTHON, _script("source_index_build.py"), "--input", str(sdd),
                 "--doc-id", f"SDD-{suffix.upper()}", "--output", str(idx)])
        args = [PYTHON, _script("score_sheet_populate.py"),
                "--bundle", str(rd / f"output-{suffix}-scoring-bundle.json"),
                "--blinding-label", label, "--run-record", str(rd / "run-record.json"),
                "--sdd-source-index", str(idx),
                "--zms-criteria", str(rd / "zms-calibration-content.json"),
                "--output", str(out)]
        if st["digests"]["intake"].get("run_integration_heavy"):
            args.append("--integration-heavy")
        d = _sh(args)
        comp = d.get("computed") or {}
        st["digests"].setdefault("sheets", {})[label] = {
            "final_score": comp.get("final_score") or comp.get("total"),
            "computed": {k: comp.get(k) for k in list(comp)[:6]}}
    st["stage"] = "S4"


def batch_lift(rd: Path, st: dict) -> None:
    out = rd / "lift-calc.json"
    if out.exists():
        return
    _sh([PYTHON, _script("lift_calculate.py"),
         "--output-a-score-sheet", str(rd / "output-a-score-sheet.xlsx"),
         "--output-b-score-sheet", str(rd / "output-b-score-sheet.xlsx"),
         "--output", str(out)])


def stage_exec_narrative_packet(rd: Path, st: dict) -> bool:
    pid = "exec_narrative"
    if packets.result_path(rd, pid).exists():
        return True
    if not packets.exists(rd, pid):
        lift = _j(rd / "lift-calc.json")
        digest = {"lift_metrics": lift.get("lift_metrics"),
                  "per_dim_mean_a": _j(rd / "output-a-scoring-bundle.json")["per_dim_mean"],
                  "per_dim_mean_b": _j(rd / "output-b-scoring-bundle.json")["per_dim_mean"],
                  "release": {lab: _release_digest(rd, lab) for lab in _labels(st)},
                  "note": "labels still blinded; write lane-neutral prose about Output A/B; "
                          "the reveal orients the lift."}
        packets.create(rd, pid, kind="exec_narrative", label="run",
                       prompt=prompts.exec_narrative_prompt(digest))
    return False


def batch_reveal_and_report(rd: Path, st: dict) -> None:
    diag = rd / "diagnostic-bundle.json"
    if not diag.exists():
        en = rd / "exec-narrative.json"
        en.write_text(json.dumps(packets.result(rd, "exec_narrative")))
        d = _sh([PYTHON, _script("lane_reveal_apply.py"),
                 "--lane-mapping", str(rd / ESCROW_NAME),
                 "--lift-calc", str(rd / "lift-calc.json"),
                 "--run-record", str(rd / "run-record.json"),
                 "--zms-summary", str(rd / "zms-calibration-summary.json"),
                 "--release-awareness-a", str(rd / "release-awareness-A.json"),
                 "--release-awareness-b", str(rd / "release-awareness-B.json"),
                 "--exec-narrative", str(en), "--output", str(diag)])
        db = _j(diag)
        s1 = db.get("section_1", {})
        st["digests"]["reveal"] = {
            "headline_lift_za_minus_ots": s1.get("methodology_lift",
                                                 d.get("headline_lift_za_minus_ots")),
            "za_total": s1.get("za_total"), "ots_total": s1.get("ots_total"),
            "lift_uncertainty": s1.get("lift_uncertainty"),
            "za_label": db.get("za_label"),
            "lift_interpretation_band": d.get("lift_interpretation_band")}
    report = rd / "diagnostic-report.docx"
    if not report.exists():
        db = _j(diag)
        za_suffix = "a" if db.get("za_label", "Output A").endswith("A") else "b"
        ots_suffix = "b" if za_suffix == "a" else "a"
        args = [PYTHON, _script("report_build_substantive.py"),
                "--bundle", str(diag),
                "--za-bundle", str(rd / f"output-{za_suffix}-scoring-bundle.json"),
                "--ots-bundle", str(rd / f"output-{ots_suffix}-scoring-bundle.json"),
                "--output", str(report)]
        if (rd / "accuracy-gate.json").exists():
            args += ["--accuracy-gate", str(rd / "accuracy-gate.json")]
        _sh(args)
    st["stage"] = "S5"


# ---------------- Mode B ----------------
def stage_review_packets(rd: Path, st: dict) -> bool:
    need = False
    for group in ("1-3", "4-7"):
        pid = f"review:{group}"
        if packets.result_path(rd, pid).exists():
            continue
        need = True
        if not packets.exists(rd, pid):
            prompt = prompts.review_prompt(
                dim_group=group, sdd_path=_lane_sdd(st, "Output A"),
                slice_path=rd / f"zms-calibration-dims-{group}.json",
                playbook_path=Path(_j(rd / "zms-calibration-content.json")
                                   ["sa_reasoning_playbook_path"]),
                brd_path=rd / "inputs" / st["files"]["brd"],
                release_digest=_release_digest(rd, "Output A"))
            packets.create(rd, pid, kind="review", label="Output A", prompt=prompt)
    return not need


def batch_mode_b_report(rd: Path, st: dict) -> None:
    bpath = rd / "sdd-review-bundle.json"
    if not bpath.exists():
        findings, recs, clar = [], [], []
        for group in ("1-3", "4-7"):
            r = packets.result(rd, f"review:{group}")
            findings += r.get("findings", [])
            recs += r.get("recommendations", [])
            clar += r.get("clarifications", [])
        blocking = [f for f in findings if f.get("is_blocking")]
        build_ready = ("not_build_ready" if blocking else
                       "build_ready_with_conditions" if any(f.get("requires") for f in findings)
                       else "build_ready")
        bundle = {"mode": "B", "run_id": st["run_id"], "build_ready": build_ready,
                  "findings": findings, "recommendations": recs, "clarifications": clar}
        bpath.write_text(json.dumps(bundle, indent=2))
        _sh([PYTHON, _script("sdd_review_validate.py"), "--bundle", str(bpath)])
        st["digests"]["review"] = {"build_ready": build_ready,
                                   "findings": len(findings), "recommendations": len(recs)}
    report = rd / "sdd-review-report.docx"
    if not report.exists():
        args = [PYTHON, _script("report_build_sdd_review.py"), "--bundle", str(bpath),
                "--output", str(report)]
        ra = rd / "release-awareness-A.json"
        if ra.exists():
            args += ["--release", str(ra)]
        _sh(args)
    st["stage"] = "S4"


# ------------------------------------------------------------------ driver
def advance(run_id: str) -> dict:
    rd = run_dir(run_id)
    st = load_state(run_id)
    if st["status"] in ("done", "error"):
        return st
    try:
        st["status"] = "running"
        batch_intake(rd, st)
        batch_zms(rd, st)
        if not stage_mapping_packets(rd, st):
            st["status"] = "awaiting_packets"; save_state(run_id, st); return st
        batch_mapping(rd, st)
        if not batch_crosswalk(rd, st):
            st["status"] = "awaiting_packets"; save_state(run_id, st); return st

        if st["mode"] == "A":
            if not stage_scoring_packets(rd, st):
                st["status"] = "awaiting_packets"; save_state(run_id, st); return st
            batch_record_and_aggregate(rd, st)
            if not stage_narrative_packets(rd, st):
                st["status"] = "awaiting_packets"; save_state(run_id, st); return st
            batch_assemble_bundles(rd, st)
            if not st.get("checkpoint_approved"):
                st["checkpoint"] = build_checkpoint(rd, st)
                if st.get("auto_approve_checkpoint"):
                    # D.5 pre-authorized at intake (hands-free mode). The panel is
                    # still built and recorded so the decision remains auditable.
                    st["checkpoint_approved"] = True
                    st["checkpoint_approved_at"] = __import__("time").strftime(
                        "%Y-%m-%dT%H:%M:%S")
                    st["checkpoint_approved_by"] = "auto (pre-authorized at intake)"
                else:
                    st["status"] = "awaiting_checkpoint"
                    save_state(run_id, st); return st
            batch_sheets(rd, st)
            batch_lift(rd, st)
            if not stage_exec_narrative_packet(rd, st):
                st["status"] = "awaiting_packets"; save_state(run_id, st); return st
            batch_reveal_and_report(rd, st)
        else:
            if not stage_review_packets(rd, st):
                st["status"] = "awaiting_packets"; save_state(run_id, st); return st
            batch_mode_b_report(rd, st)

        st["status"] = "done"
        save_state(run_id, st)
        return st
    except Exception as e:
        st["status"] = "error"
        st["error"] = f"{e}"
        st["traceback"] = traceback.format_exc()[-3000:]
        save_state(run_id, st)
        return st
