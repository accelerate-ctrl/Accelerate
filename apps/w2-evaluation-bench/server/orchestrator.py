"""Deterministic pipeline orchestrator.

advance(run_id) executes every batch whose inputs are ready, in order, and
stops when it must wait: on open work packets (model judgment, operator-side
runner) or the mandatory D.5 operator approval. It is safe to call repeatedly
(idempotent per batch: each batch checks its own output artifact first).

Model judgment NEVER happens here. The server holds no model client at all.
"""
from __future__ import annotations
import json
import os
import subprocess
import traceback
from pathlib import Path

from .config import SCRIPTS, ZMS_ROOT, PYTHON, ESCROW_NAME, EVAL_PROTOCOL
from . import prompts, packets, bundle_assemble
from . import consensus as consensus_mod
from .storage import run_dir, load_state, save_state

import contracts
import pass_accumulate      # five-pass legacy path (frozen; EVAL_PROTOCOL=five-pass)
import judge_accumulate
import nlp                  # pre-intelligence layer (deterministic; approved plan)
import source_index_build

DUAL = (EVAL_PROTOCOL == "dual-judge")
GROUP_DIMS = {"1-3": ("1", "2", "3"), "4-7": ("4", "5", "6", "7")}
SUB_MAX_BY_KEY = {k: float(mx) for subs in bundle_assemble.SUBS.values()
                  for k, mx in subs}


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
            # Pre-intelligence: add deterministic high-precision search
            # variants per mechanism (additive fields; engine resolve reads
            # its own fields untouched). The evidence packet embeds these.
            qdoc = _j(q)
            qdoc["queries"] = nlp.enrich_queries(qdoc.get("queries", []))
            q.write_text(json.dumps(qdoc, indent=1))
        ev = rd / f"release-evidence-{lane}.json"
        if st.get("live_evidence"):
            pid = f"evidence:{label}"
            # Self-crawl first (semi-intelligent layer): the server gathers
            # the *.salesforce.com evidence itself from the enriched queries.
            # Falls back to a web-capable judge packet when the crawl yields
            # nothing (offline / blocked egress / no on-domain results) or
            # when pinned to the legacy path with W2_EVIDENCE_SOURCE=judge.
            if (not ev.exists() and not packets.exists(rd, pid)
                    and os.environ.get("W2_EVIDENCE_SOURCE", "crawl") != "judge"):
                try:
                    crawled = nlp.gather_evidence(_j(q).get("queries", []))
                except Exception:
                    crawled = {"evidence": {}}
                if any((crawled.get("evidence") or {}).values()):
                    ev.write_text(json.dumps(
                        {"lane": lane, "as_of": crawled.get("as_of"),
                         "source": crawled.get("source", "self-crawl"),
                         "evidence": crawled["evidence"]}))
            if not ev.exists():
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
                                          "source": "judge",
                                          "evidence": res.get("evidence", {})}))
            # Pre-intelligence: advisory review of the web evidence (snippet
            # relevance + R23 domain pre-check) — crawled or judge-gathered
            # alike. Separate artifact + digest; nothing dropped — the R23
            # validator stays the enforcement point.
            review = nlp.review_evidence(_j(ev).get("evidence", {}),
                                         _j(q).get("queries", []))
            (rd / f"release-evidence-review-{lane}.json").write_text(
                json.dumps(review, indent=1))
            st["digests"].setdefault("release_review", {})[label] = review["summary"]
            st["digests"].setdefault("release_evidence_source", {})[label] = \
                _j(ev).get("source", "judge")
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
    """Scoring packets, protocol-dispatched: dual-judge (v2.0 product) or the
    frozen five-pass legacy path (EVAL_PROTOCOL=five-pass)."""
    if DUAL:
        return stage_scoring_packets_dual(rd, st)
    return stage_scoring_packets_fivepass(rd, st)


def _integration_heavy(st: dict) -> bool:
    return bool((st.get("digests", {}).get("intake") or {}).get("run_integration_heavy"))


def _group_ctx(rd: Path, st: dict, group: str) -> dict:
    """Per (dim-group) consensus context: the calibration slice's criteria,
    the sub maxima, the group dims, and integration-aware dim maxima."""
    criteria = _j(rd / f"zms-calibration-dims-{group}.json")["applicable_criteria"]
    dims = list(GROUP_DIMS[group])
    ih = _integration_heavy(st)
    return {"criteria": criteria, "dims": dims,
            "sub_max": dict(SUB_MAX_BY_KEY),
            "dim_max": {d: contracts.dim_max(int(d), ih) for d in dims}}


def _lane_rr_floor(rd: Path, st: dict, label: str) -> tuple[float, object]:
    """The lane's capped RR total and Dim-4 floor cap — the same values the
    v1.1 path carried in pass-packet meta; under dual-judge they are applied
    once, post-merge, by the consensus engine (TR-14)."""
    lane = "A" if label.endswith("A") else "B"
    mapping = st["digests"]["mapping"][label]
    rap = rd / f"release-awareness-{lane}.json"
    rr = (_j(rap).get("summary", {}).get("rr_deductions_capped_total", 0)
          if rap.exists() else 0)
    return float(rr or 0), mapping.get("dim_4_floor_cap")


def _pre_analysis(rd: Path, st: dict, label: str) -> dict:
    """Build (once) and load the lane's pre-intelligence artifact: document
    model, requirement registry, per-criterion evidence candidates,
    BRD<->SDD traceability, guardrail lint. Deterministic and blinded (reads
    only lane-labelled documents); persisted as pre-analysis-<lane>.json and
    summarized into the run digests for the console."""
    lane = "A" if label.endswith("A") else "B"
    path = rd / f"pre-analysis-{lane}.json"
    if path.exists():
        return _j(path)
    crits = {g: _j(rd / f"zms-calibration-dims-{g}.json")["applicable_criteria"]
             for g in ("1-3", "4-7")}
    pre = nlp.build_pre_analysis(
        brd_text=(rd / "inputs" / st["files"]["brd"]).read_text(errors="replace"),
        sdd_text=_lane_sdd(st, label).read_text(errors="replace"),
        criteria_by_group=crits)
    path.write_text(nlp.pre_analysis.to_json(pre))
    st.setdefault("digests", {}).setdefault("pre_analysis", {})[label] = pre["summary"]
    return pre


def stage_scoring_packets_dual(rd: Path, st: dict) -> bool:
    """8 pass packets (2 lanes x 2 dim-groups x 2 judges). The two packets of
    a (lane, group) are BYTE-IDENTICAL in prompt — the judge lives only in
    packet meta (PRD FR-3). True when all results are in."""
    import pass_plan as pp
    need = False
    for label in _labels(st):
        lane = "A" if label.endswith("A") else "B"
        mapping = st["digests"]["mapping"][label]
        rel = _release_digest(rd, label)
        rr, floor_cap = _lane_rr_floor(rd, st, label)
        for group in ("1-3", "4-7"):
            slice_ids = [c["id"] for c in
                         _j(rd / f"zms-calibration-dims-{group}.json")["applicable_criteria"]]
            plans = pp.pass_plan(st["run_id"] + f":{lane}:{group}", slice_ids)
            plan = plans[0] if isinstance(plans, list) and plans else {}
            prompt = None
            for judge in contracts.JUDGES:
                pid = f"pass:{label}:{group}:{judge}"
                if packets.result_path(rd, pid).exists():
                    continue
                need = True
                st["stage"] = "S3"  # dual scoring in flight (console stage rail)
                if not packets.exists(rd, pid):
                    if prompt is None:  # built once -> byte-identical across judges
                        pre = _pre_analysis(rd, st, label)
                        prompt = prompts.pass_prompt_dual(
                            run_id=st["run_id"], label=label, dim_group=group,
                            sdd_path=_lane_sdd(st, label),
                            slice_path=rd / f"zms-calibration-dims-{group}.json",
                            playbook_path=Path(_j(rd / "zms-calibration-content.json")
                                               ["sa_reasoning_playbook_path"]),
                            core_ref=SCRIPTS.parent / "references" / "section-d-core.md",
                            dims_ref=SCRIPTS.parent / "references" / f"section-d-dims-{group}.md",
                            plan=plan, mapping_digest=mapping, release_digest=rel,
                            pre_analysis=nlp.prompt_digest(pre, group))
                    packets.create(rd, pid, kind="pass", label=label, prompt=prompt,
                                   meta={"lane": lane, "dim_group": group,
                                         "judge": judge, "floor_cap": floor_cap,
                                         "rr_capped_total": rr})
    return not need


def batch_consensus(rd: Path, st: dict) -> bool:
    """S3.5 (Application Flow §4): persist both scorecards verbatim, diff,
    reconcile divergences via ONE blinded Judge-A packet per (lane, group),
    merge deterministically, write consensus/<lane>_<group>.json. True when
    every group's consensus record exists."""
    done = True
    for label in _labels(st):
        lane = "A" if label.endswith("A") else "B"
        rr, floor_cap = _lane_rr_floor(rd, st, label)
        for group in ("1-3", "4-7"):
            cpath = judge_accumulate.consensus_path(rd, lane, group)
            if cpath.exists():
                continue
            st["stage"] = "S3.5"  # consensus/reconciliation in flight
            # 1. persist scorecards VERBATIM before any diff (Backend §5)
            cards = {}
            for judge in contracts.JUDGES:
                res = packets.result(rd, f"pass:{label}:{group}:{judge}")
                judge_accumulate.persist_scorecard(rd, lane, group, judge, res)
            cards = judge_accumulate.load_scorecards(rd, lane, group)
            ctx = _group_ctx(rd, st, group)
            d = consensus_mod.diff(cards, ctx["criteria"], ctx["sub_max"],
                                   ctx["dims"], ctx["dim_max"])
            # Pre-intelligence post-judgment check (approved plan, N5):
            # agreed affirmative verdicts whose anchor shares zero judgeable
            # terms with the criterion join the SAME reconcile packet as a
            # review class — the intelligent layer confirms with a citation
            # or records a dissent. Never decided here.
            weak = nlp.review_anchor_quality(cards, d["criteria"], ctx["criteria"])
            crit_items = {**d["criteria"], **weak}
            divergent = bool(crit_items or d["subs"])
            rulings = None
            rpid = f"reconcile:{label}:{group}"
            if divergent:
                if not packets.result_path(rd, rpid).exists():
                    if not packets.exists(rd, rpid):
                        sub_items = {ik: {contracts.JUDGES[0]: v[contracts.JUDGES[0]],
                                          contracts.JUDGES[1]: v[contracts.JUDGES[1]],
                                          "max": v.get("_max")}
                                     for ik, v in d["subs"].items()}
                        packets.create(
                            rd, rpid, kind="reconcile", label=label,
                            prompt=prompts.reconcile_prompt(
                                label=label, dim_group=group,
                                crit_items=crit_items, sub_items=sub_items,
                                sdd_path=_lane_sdd(st, label)),
                            meta={"lane": lane, "dim_group": group,
                                  "judge": contracts.JUDGES[0]})
                    done = False
                    continue
                rulings = packets.result(rd, rpid).get("rulings") or {}
            try:
                rec = consensus_mod.merge(
                    cards, rulings, criteria=ctx["criteria"],
                    sub_max=ctx["sub_max"], dims=ctx["dims"],
                    dim_max=ctx["dim_max"], lane=lane, dim_group=group,
                    rr_capped_total=rr, floor_cap=floor_cap,
                    review_items=set(weak))
            except ValueError as e:
                # Semantically invalid rulings (unknown ruling, out-of-bounds
                # meet_between, missing item): reopen the reconcile packet for
                # a fresh judged attempt; after 3 invalid attempts, halt loudly.
                key = f"{lane}:{group}"
                retries = st.setdefault("reconcile_retries", {})
                n = int(retries.get(key, 0)) + 1
                retries[key] = n
                if n >= 3:
                    raise RuntimeError(
                        f"reconcile for {label} dims {group} produced invalid "
                        f"rulings {n} times; last error: {e}")
                packets.result_path(rd, rpid).unlink(missing_ok=True)
                done = False
                continue
            cpath.parent.mkdir(parents=True, exist_ok=True)
            cpath.write_text(consensus_mod.to_json(rec))
    return done


def batch_judge_aggregate(rd: Path, st: dict) -> None:
    """Collapse each lane's two consensus records into the bundle-facing
    aggregate + lane-level agreement stats (TR-21: merged, never recomputed)."""
    for label in _labels(st):
        lane = "A" if label.endswith("A") else "B"
        agg_path = rd / f"lane-{lane}-judge-aggregate.json"
        if agg_path.exists():
            continue
        agg = judge_accumulate.aggregate(lane, rd, _integration_heavy(st))
        agg["agreement_stats"] = consensus_mod.merge_lane_stats(agg["group_stats"])
        agg_path.write_text(json.dumps(agg, indent=2, sort_keys=True))
        s = agg["agreement_stats"]
        # Per-dimension judge/consensus positions for the console's concurrence
        # meter (UI/UX §3.4). ADDITIVE key on the §2 consensus digest — no
        # existing endpoint carries per-dim judge data (errata G-1).
        ja, jb = contracts.JUDGES
        jr = agg["judge_runs_by_dimension"]
        rpd = s.get("verdict_agreement_rate_per_dim") or {}
        ddims = set()
        for dd in agg.get("dissents") or []:
            cid = dd.get("criterion_id") or ""
            sk = dd.get("sub_key") or ""
            if cid:
                ddims.add(cid[0])
            elif sk.startswith("sub:"):
                ddims.add(sk.split(":")[1])
        ih = _integration_heavy(st)
        per_dim = {d: {"cc": (jr.get(ja) or {}).get(d),
                       "gm": (jr.get(jb) or {}).get(d),
                       "con": (jr.get("consensus") or {}).get(d),
                       "max": contracts.dim_max(int(d), ih),
                       "conc": agg["per_dim_agreement"].get(d),
                       "agree": rpd.get(d),
                       "dissent": d in ddims}
                   for d in map(str, range(1, 8))}
        st["digests"].setdefault("consensus", {})[label] = {
            "verdict_agreement_rate": s.get("verdict_agreement_rate"),
            "score_concordance": s.get("score_concordance"),
            "agreement_overall": s.get("agreement_overall"),
            "divergences": s.get("divergence_count"),
            "dissents": s.get("dissent_count"),
            "reliability": s.get("reliability_label"),
            "per_dim": per_dim}


def stage_scoring_packets_fivepass(rd: Path, st: dict) -> bool:
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
            # Per-dimension digest: up to 3 criteria per dim so every dimension is
            # represented regardless of prompt-size trimming (the narrative needs
            # breadth across dims, not exhaustiveness — the bundle carries that).
            by_dim: dict[str, dict] = {str(d): {} for d in range(1, 8)}
            if DUAL:
                # v4.7: the digest comes from the CONSENSUS records — the
                # narrative must cite anchors that actually entered the
                # consensus, or R12/R13/R25 validate against ghosts (C-4).
                agg = _j(rd / f"lane-{lane}-judge-aggregate.json")
                for cid, rec in (agg.get("consensus_verdicts") or {}).items():
                    dim = cid[0]
                    if not rec or len(by_dim.get(dim, {})) >= 3:
                        continue
                    by_dim.setdefault(dim, {})[cid] = {
                        "verdict": rec.get("verdict"),
                        "evidence_anchor": (rec.get("evidence_anchor") or "")[:140],
                        "sdd_ref": rec.get("sdd_ref"),
                        "provenance": (agg.get("consensus_provenance") or {}).get(cid)}
                aggregate_digest = {
                    "per_dim_mean": agg["per_dim_mean"],
                    "per_dim_agreement": agg["per_dim_agreement"],
                    "agreement_stats": {k: agg["agreement_stats"].get(k) for k in
                                        ("verdict_agreement_rate", "score_concordance",
                                         "agreement_overall", "dissent_count",
                                         "reliability_label")}}
            else:
                agg = _j(rd / f"lane-{lane}-pass-aggregate.json")
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
                aggregate_digest = {k: agg[k] for k in ("per_dim_mean", "per_dim_stddev",
                                                        "per_dim_variance_flag")}
            coding_digest = {cid: rec for dim in sorted(by_dim) for cid, rec in by_dim[dim].items()}
            prompt = prompts.narrative_prompt(
                label=label,
                aggregate=aggregate_digest,
                coding_digest=coding_digest,
                brd_path=rd / "inputs" / st["files"]["brd"])
            packets.create(rd, pid, kind="narrative", label=label, prompt=prompt)
    return not need


def _judge_models_from_packets(rd: Path, label: str) -> dict:
    """Judge model ids for header.judge_models, read from the pass packets'
    usage ledger entries (the runner reports the model per call)."""
    out = {}
    for judge in contracts.JUDGES:
        for group in ("1-3", "4-7"):
            p = packets.result_path(rd, f"pass:{label}:{group}:{judge}")
            if not p.exists():
                continue
            u = (_j(p).get("usage") or {})
            m = u.get("model")
            if isinstance(m, list):
                m = m[0] if m else None
            if m:
                out[judge] = m
                break
        out.setdefault(judge, judge)
    return out


def batch_assemble_bundles(rd: Path, st: dict) -> None:
    calibration = _j(rd / "zms-calibration-content.json")
    run_record = _j(rd / "run-record.json")
    for label in _labels(st):
        lane = "A" if label.endswith("A") else "B"
        suffix = "a" if lane == "A" else "b"
        bpath = rd / f"output-{suffix}-scoring-bundle.json"
        if bpath.exists():
            continue
        release = {}
        rp = rd / f"release-awareness-{lane}.json"
        if rp.exists():
            release = _j(rp)
        mapping = _j(rd / f"section-c-output-{suffix}.json")
        if DUAL:
            agg = _j(rd / f"lane-{lane}-judge-aggregate.json")
            bundle = bundle_assemble.assemble_v47(
                run_id=st["run_id"], label=label, aggregate=agg,
                agreement_stats=agg["agreement_stats"],
                narrative=packets.result(rd, f"narrative:{label}"),
                calibration=calibration, mapping=mapping, release=release,
                run_record=run_record,
                judge_models=_judge_models_from_packets(rd, label))
        else:
            agg = _j(rd / f"lane-{lane}-pass-aggregate.json")
            pass_results = [packets.result(rd, f"pass:{label}:{g}:{n}")
                            for g in ("1-3", "4-7") for n in range(1, 6)]
            bundle = bundle_assemble.assemble(
                run_id=st["run_id"], label=label, aggregate=agg,
                pass_results=pass_results, narrative=packets.result(rd, f"narrative:{label}"),
                calibration=calibration, mapping=mapping, release=release,
                run_record=run_record)
        bundle_assemble.write_bundle(bpath, bundle)
    st["stage"] = "S3.5" if DUAL else "S3"


def build_checkpoint(rd: Path, st: dict) -> dict:
    """The blinded D.5 panel (procedures section D.5). v4.7 (Backend §8): the
    five-pass variance flags and pass-timing flags are replaced by the
    dual-judge signals — agreement rate, dissent count, dissent-touched dims."""
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
        entry = {
            "total": round(sum(b["per_dim_mean"].values()), 1),
            "per_dim_mean": b["per_dim_mean"],
            "trust_deductions": sum(1 for x in b["deductions"] if x["id"].startswith("TRUST")),
            "rr_deductions": sum(1 for x in b["deductions"] if x["id"].startswith("RR")),
            "mapping": st["digests"]["mapping"][label],
            "release_summary": {k: rel.get(k) for k in ("findings_total", "by_status",
                                                        "rr_deductions_capped_total")},
        }
        if DUAL:
            cons = st["digests"].get("consensus", {}).get(label, {})
            dissent_dims = sorted({(d.get("criterion_id") or
                                    (d.get("sub_key") or "sub::").split(":")[1] or "?")[0]
                                   if d.get("criterion_id") else
                                   (d.get("sub_key") or "sub:?:").split(":")[1]
                                   for d in (b.get("dissents") or [])})
            entry.update({
                "agreement_rate": cons.get("verdict_agreement_rate"),
                "score_concordance": cons.get("score_concordance"),
                "agreement_overall": cons.get("agreement_overall"),
                "dissent_count": cons.get("dissents"),
                "dissent_dims": dissent_dims,
                "reliability": cons.get("reliability"),
            })
        else:
            entry.update({
                "variance_flags": [d for d, f in b["per_dim_variance_flag"].items() if f],
                "pass_timing_flags": st["digests"].get("aggregate", {}).get(label, {})
                                      .get("pass_timing_flags", []),
            })
        panel["lanes"][label] = entry
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
    if DUAL:
        # v4.7: lift reads the scoring BUNDLES (consensus headline + per-judge
        # lifts + band; TR-19). The sheet is presentation-only (errata V-2).
        args = [PYTHON, _script("lift_calculate.py"),
                "--bundle-a", str(rd / "output-a-scoring-bundle.json"),
                "--bundle-b", str(rd / "output-b-scoring-bundle.json"),
                "--output", str(out)]
        if _integration_heavy(st):
            args.append("--integration-heavy")
        _sh(args)
    else:
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
        if DUAL:
            # Concurrence context for the executive narrative (still blinded:
            # judge lifts are lane-neutral A-minus-B figures pre-reveal).
            digest["cross_model_concurrence"] = {
                "agreement_overall": lift.get("agreement_overall"),
                "per_lane": st["digests"].get("consensus", {}),
                "note": "two independent model families scored from identical "
                        "blinded packets; dissents were resolved conservatively "
                        "and are preserved in the report annex."}
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
            "lift_interpretation_band": d.get("lift_interpretation_band"),
            # v4.7 (Backend §2/§9): per-judge lifts, band, run agreement
            "judge_lifts": s1.get("judge_lifts"),
            "lift_band": s1.get("lift_band"),
            "agreement_overall": s1.get("agreement_overall")}
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
    """Mode B review packets. Dual-judge: 2 groups x 2 judges = 4 packets,
    byte-identical prompts per group, judge in meta (PRD FR-7). Five-pass
    legacy: the original 2 single-judge packets."""
    need = False
    judges = list(contracts.JUDGES) if DUAL else [None]
    for group in ("1-3", "4-7"):
        prompt = None
        for judge in judges:
            pid = f"review:{group}:{judge}" if judge else f"review:{group}"
            if packets.result_path(rd, pid).exists():
                continue
            need = True
            if not packets.exists(rd, pid):
                if prompt is None:  # built once -> byte-identical across judges
                    pre = (_pre_analysis(rd, st, "Output A") if DUAL else None)
                    prompt = prompts.review_prompt(
                        dim_group=group, sdd_path=_lane_sdd(st, "Output A"),
                        slice_path=rd / f"zms-calibration-dims-{group}.json",
                        playbook_path=Path(_j(rd / "zms-calibration-content.json")
                                           ["sa_reasoning_playbook_path"]),
                        brd_path=rd / "inputs" / st["files"]["brd"],
                        release_digest=_release_digest(rd, "Output A"),
                        pre_analysis=(nlp.prompt_digest(pre, group) if pre else ""))
                meta = {"dim_group": group}
                if judge:
                    meta["judge"] = judge
                packets.create(rd, pid, kind="review", label="Output A",
                               prompt=prompt, meta=meta)
    return not need


# Conservative order for Mode B finding verdicts (errata Q4): the MORE
# critical claim survives a dissent — risk > gap > strength.
_FINDING_SEVERITY = {"risk": 2, "gap": 1, "strength": 0}


def _mode_b_pool(rd: Path) -> dict:
    """Pool each judge's findings/recommendations/clarifications across both
    groups, keyed by judge. Returns {judge: {"findings": {zms_lens: finding},
    "recs_by_lens": {zms_lens: [rec,...]}, "clarifications": [...]}}."""
    pool = {}
    for judge in contracts.JUDGES:
        findings_by_lens, recs_by_lens, clar = {}, {}, []
        fid_to_lens = {}
        for group in ("1-3", "4-7"):
            r = packets.result(rd, f"review:{group}:{judge}")
            for f in r.get("findings", []):
                lens = f.get("zms_lens") or f.get("id")
                findings_by_lens[lens] = f
                if f.get("id"):
                    fid_to_lens[f["id"]] = lens
            for rec in r.get("recommendations", []):
                lens = fid_to_lens.get(rec.get("traces_to_finding"))
                if lens:
                    recs_by_lens.setdefault(lens, []).append(rec)
            clar += r.get("clarifications", [])
        pool[judge] = {"findings": findings_by_lens, "recs_by_lens": recs_by_lens,
                       "clarifications": clar}
    return pool


def batch_mode_b_consensus(rd: Path, st: dict) -> bool:
    """Mode B S3.5 (Application Flow §5, errata Q4): findings matched by
    zms_lens; matched-different AND one-sided findings all go to ONE
    reconcile:review packet; dissents resolve to the more critical verdict and
    flag the finding contested. Writes review-consensus.json; True when done."""
    out = rd / "review-consensus.json"
    if out.exists():
        return True
    ja, jb = contracts.JUDGES
    pool = _mode_b_pool(rd)
    lenses = sorted(set(pool[ja]["findings"]) | set(pool[jb]["findings"]))

    divergent = {}
    for lens in lenses:
        fa, fb = pool[ja]["findings"].get(lens), pool[jb]["findings"].get(lens)
        if fa is None or fb is None or fa.get("verdict") != fb.get("verdict"):
            divergent[lens] = {ja: fa, jb: fb}

    rulings = {}
    rpid = "reconcile:review"
    if divergent:
        if not packets.result_path(rd, rpid).exists():
            if not packets.exists(rd, rpid):
                packets.create(
                    rd, rpid, kind="reconcile", label="Output A",
                    prompt=prompts.reconcile_prompt(
                        label="Output A", dim_group="review",
                        crit_items=divergent, sub_items={},
                        sdd_path=_lane_sdd(st, "Output A")),
                    meta={"judge": ja, "dim_group": "review"})
            return False
        rulings = packets.result(rd, rpid).get("rulings") or {}

    findings, recs, dissents = [], [], []
    seq_by_dim: dict[str, int] = {}
    for lens in lenses:
        fa, fb = pool[ja]["findings"].get(lens), pool[jb]["findings"].get(lens)
        base, prov, judge_entries, contested = None, "agreed", None, False
        if lens not in divergent:
            base, prov = dict(fa), "agreed"
            src_judge = ja
        else:
            ruling = rulings.get(lens) or {}
            r = ruling.get("ruling")
            judge_entries = {ja: fa, jb: fb}
            if r == "adopt_claude" and fa is not None:
                base, prov, src_judge = dict(fa), "adopt_claude", ja
            elif r == "adopt_gemini" and fb is not None:
                base, prov, src_judge = dict(fb), "adopt_gemini", jb
            elif r == "meet_between" and (fa is not None or fb is not None):
                # meet_between on findings: the middle of risk/strength is gap
                base = dict(fa or fb)
                base["verdict"] = "gap"
                prov, src_judge = "meet_between", ja
            else:
                # dissent, missing ruling, or an adopt_* pointing at a side
                # that reported nothing: conservative — the MORE critical
                # claim survives (Q4); an absent side is least critical.
                sa = _FINDING_SEVERITY.get((fa or {}).get("verdict", ""), -1)
                sb = _FINDING_SEVERITY.get((fb or {}).get("verdict", ""), -1)
                base = dict(fa if sa >= sb else fb)
                src_judge = ja if sa >= sb else jb
                prov, contested = "dissent", True
                dissents.append({
                    "zms_lens": lens, ja: fa, jb: fb,
                    "conservative_resolution": {"verdict": base.get("verdict")},
                    "why_unresolved": ruling.get("rationale")
                    or "judges could not be reconciled on the cited evidence"})
        if base is None:
            continue
        if fa is not None and fb is not None and base.get("is_blocking") is not None:
            base["is_blocking"] = bool((fa or {}).get("is_blocking")
                                       or (fb or {}).get("is_blocking"))
        dim = str(base.get("dimension", lens[0] if lens else "0"))
        seq_by_dim[dim] = seq_by_dim.get(dim, 0) + 1
        new_id = f"F-{dim}{seq_by_dim[dim]:02d}"
        base["id"] = new_id
        base["zms_lens"] = lens
        base["judge_provenance"] = prov
        if judge_entries:
            base["judge_entries"] = judge_entries
        if contested:
            base["contested"] = True
        findings.append(base)
        # recommendations follow the judge whose finding text was kept
        for rec in pool[src_judge]["recs_by_lens"].get(lens, []):
            rec = dict(rec)
            rec["traces_to_finding"] = new_id
            if contested:
                rec["contested"] = True
            recs.append(rec)

    for i, rec in enumerate(recs, 1):
        rec["id"] = f"R-{i:02d}"
    clar = pool[ja]["clarifications"] + [
        c for c in pool[jb]["clarifications"] if c not in pool[ja]["clarifications"]]

    non_na = len(lenses) or 1
    agreed_n = sum(1 for f in findings if f.get("judge_provenance") == "agreed")
    consensus_doc = {
        "findings": findings, "recommendations": recs, "clarifications": clar,
        "dissents": dissents,
        "stats": {"verdict_agreement_rate": round(agreed_n / non_na, 3),
                  "score_concordance": None,
                  "agreement_overall": round(agreed_n / non_na, 3),
                  "divergence_count": len(divergent),
                  "dissent_count": len(dissents),
                  "non_na_criteria": len(lenses),
                  "note": ("Mode B carries no scores, so agreement_overall is "
                           "the verdict agreement rate alone (errata Q4).")},
    }
    out.write_text(json.dumps(consensus_doc, indent=2, sort_keys=True))
    return True


def batch_mode_b_report(rd: Path, st: dict) -> None:
    bpath = rd / "sdd-review-bundle.json"
    if not bpath.exists():
        dissents = []
        stats = None
        if DUAL:
            doc = _j(rd / "review-consensus.json")
            findings = doc["findings"]
            recs = doc["recommendations"]
            clar = doc["clarifications"]
            dissents = doc["dissents"]
            stats = doc["stats"]
        else:
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
        if DUAL:
            # Backend Schema §11: dual-judge review deltas — dissents at top
            # level, judge provenance on findings (already stamped by the
            # consensus batch), agreement stats block, panel label.
            bundle["dissents"] = dissents
            bundle["agreement_stats"] = stats
            bundle["evaluator_model"] = st.get("evaluator_model")
        bpath.write_text(json.dumps(bundle, indent=2))
        _sh([PYTHON, _script("sdd_review_validate.py"), "--bundle", str(bpath)])
        st["digests"]["review"] = {"build_ready": build_ready,
                                   "findings": len(findings), "recommendations": len(recs),
                                   **({"dissents": len(dissents),
                                       "verdict_agreement_rate":
                                           (stats or {}).get("verdict_agreement_rate")}
                                      if DUAL else {})}
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
def _auto_execute_open(rd: Path) -> int:
    """Autonomous mode: the app executes its own packets in-process with the
    deterministic screener (server/auto_judge.py). Results pass the same
    shape validation a runner-posted result would; a failure marks the run
    error rather than storing a malformed result. Returns packets completed."""
    from . import auto_judge, packet_shapes
    n = 0
    for p in packets.open_packets(rd):
        pid = p["packet_id"]
        packet = packets.claim(rd, pid, auto_judge.RUNNER_ID)
        result = auto_judge.execute(packet)
        usage = auto_judge.usage_for(packet)
        problem = (packet_shapes.validate_result(packet.get("kind"), result,
                                                 packet.get("meta"))
                   or packet_shapes.validate_judge_provenance(
                       packet.get("kind"), packet.get("meta"), usage))
        if problem:
            raise RuntimeError(f"autonomous screener produced an invalid "
                               f"{packet.get('kind')} result ({pid}): {problem}")
        packets.complete(rd, pid, result, usage)
        n += 1
    return n


def advance(run_id: str) -> dict:
    """Stage driver. For autonomous runs the server IS the intelligence
    layer: every time the pipeline pauses for packets, the deterministic
    screener executes them in-process and the pipeline resumes — a run
    completes with zero external judges, zero model calls."""
    st = _advance_once(run_id)
    if st.get("evaluator_model") == "autonomous":
        rd = run_dir(run_id)
        guard = 0
        while st.get("status") == "awaiting_packets" and guard < 60:
            guard += 1
            try:
                if not _auto_execute_open(rd):
                    break
            except Exception as e:
                st = load_state(run_id)
                st["status"] = "error"
                st["error"] = f"autonomous screener: {e}"
                save_state(run_id, st)
                return st
            st = _advance_once(run_id)
    return st


def _advance_once(run_id: str) -> dict:
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
            if DUAL:
                # S3.5 — evidence-ruled consensus; may create reconcile packets
                if not batch_consensus(rd, st):
                    st["status"] = "awaiting_packets"; save_state(run_id, st); return st
                batch_judge_aggregate(rd, st)
            else:
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
            if DUAL and not batch_mode_b_consensus(rd, st):
                # divergent findings -> one reconcile:review packet round-trip
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
