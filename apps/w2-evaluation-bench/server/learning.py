"""Learning loop 1 — feedback ledger + gated screener calibration.

Every AI-judged consensus becomes training data: for each criterion the
ledger pairs the FINAL evidence-ruled verdict with the raw features the
autonomous screener would have used (component present/partial/absent
counts, top evidence-candidate strength). The calibrator grid-searches the
screener's two thresholds against that history and proposes new params.

Safety covenant (what makes self-training honest here):
- The ledger is append-only raw fact; nothing is decided at record time.
- Proposed params NEVER apply blind: apply() re-runs the gold-corpus
  verdict benchmark UNDER the candidate params and rejects any update that
  drops the verdicts component below the 95% floor — the app can only get
  better on history while never getting worse on the gold contract.
- Mock/screener-generated runs are excluded from fitting by default
  (learning from placeholders would be circular); W2_LEARN_FROM_MOCK=1
  exists solely so the smoke can exercise the loop offline.
- params.json is version-stamped and recorded in run provenance.
"""
from __future__ import annotations
import json
import time
from pathlib import Path

from .config import DATA_DIR

LEARN_DIR = DATA_DIR / "learning"
LEDGER = LEARN_DIR / "ledger.jsonl"
PARAMS = LEARN_DIR / "params.json"
DEFAULTS = {"min_matched_terms": 2, "present_deficit_div": 3}
GOLD_FLOOR = 0.95


# ------------------------------------------------------------------ record
def record_consensus(rd: Path, st: dict, label: str, group: str,
                     cards: dict, rec: dict, criteria: list, sdd_path: Path) -> None:
    """Append one ledger row per criterion of a freshly merged consensus.
    Best-effort by design: a ledger problem must never fail a run."""
    try:
        from . import auto_judge
        sdd = Path(sdd_path).read_text()
        sent_terms = auto_judge._sentence_terms(sdd)
        from nlp.evidence_locator import locate_candidates
        located = locate_candidates(sdd, criteria)["per_criterion"]
        # merge() record shape: items[cid] = {"provenance": ..., "consensus":
        # {"verdict": ...}} (server/consensus.py)
        items = rec.get("items") or {}
        final_by_cid = {cid: (v.get("consensus") or {})
                        for cid, v in items.items()}
        judges = sorted(cards)
        engines = set()
        for j in judges:  # true engine from the pass packet's usage ledger
            try:
                up = rd / "packets" / f"pass:{label}:{group}:{j}.result.json"
                if not up.exists():  # packet ids are sanitized on disk; scan
                    hits = list((rd / "packets").glob(f"*{group}*{j}*.result.json"))
                    up = hits[0] if hits else up
                engines.add((json.loads(up.read_text()).get("usage") or {})
                            .get("engine") or "?")
            except Exception:
                engines.add("?")
        engines = sorted(engines)
        LEARN_DIR.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a", encoding="utf-8") as fh:
            for c in criteria:
                cid = c["id"]
                fin = (final_by_cid.get(cid) or {}).get("verdict")
                if fin not in ("Present", "Partial", "Absent"):
                    continue
                comps = (c.get("depth_indicator_components")
                         or [c.get("depth_indicator", "")])
                stats = [auto_judge._comp_status(x, sent_terms) for x in comps]
                cands = located.get(cid, {}).get("candidates", [])
                row = {
                    "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "run": st.get("run_id"), "label": label, "group": group,
                    "cid": cid,
                    "engines": engines or [st.get("evaluator_model", "?")],
                    "n_comps": len(comps),
                    "n_present": stats.count("present"),
                    "n_partial": stats.count("partial"),
                    "n_absent": stats.count("absent"),
                    "top_matched": (cands[0].get("matched_terms", 0)
                                    if cands else 0),
                    "judge_verdicts": {j: ((cards.get(j, {}).get("verdicts") or {})
                                           .get(cid) or {}).get("verdict")
                                       for j in judges},
                    "final": fin,
                }
                fh.write(json.dumps(row, sort_keys=True) + "\n")
    except Exception:
        pass  # ledger is advisory infrastructure, never a run dependency


# --------------------------------------------------------------------- fit
def _predict(row: dict, mmt: int, pdd: int) -> str:
    """Screener-A verdict under candidate params, from ledger features —
    the exact rule auto_judge applies, re-expressed over stored counts."""
    n, np_, npa, nab = (row["n_comps"], row["n_present"],
                        row["n_partial"], row["n_absent"])
    if nab == 0 and row["top_matched"] >= mmt \
            and np_ >= max(1, n - n // pdd):
        return "Present"
    if np_ or npa:
        return "Partial"
    return "Absent"


def load_rows(*, include_mock: bool = False) -> list[dict]:
    if not LEDGER.exists():
        return []
    rows = []
    for line in LEDGER.read_text().splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        engines = set(r.get("engines") or [])
        if not include_mock and engines & {"mock", "auto-screener", "autonomous"}:
            continue
        rows.append(r)
    return rows


def fit(rows: list[dict]) -> dict:
    """Grid-search the two screener thresholds against consensus history.
    -> {"params", "accuracy", "baseline_accuracy", "n"}"""
    if not rows:
        return {"params": dict(DEFAULTS), "accuracy": None,
                "baseline_accuracy": None, "n": 0}
    def acc(mmt, pdd):
        hit = sum(1 for r in rows if _predict(r, mmt, pdd) == r["final"])
        return hit / len(rows)
    base = acc(DEFAULTS["min_matched_terms"], DEFAULTS["present_deficit_div"])
    best, best_a = dict(DEFAULTS), base
    for mmt in (1, 2, 3):
        for pdd in (2, 3, 4):
            a = acc(mmt, pdd)
            if a > best_a + 1e-9:
                best, best_a = {"min_matched_terms": mmt,
                                "present_deficit_div": pdd}, a
    return {"params": best, "accuracy": round(best_a, 4),
            "baseline_accuracy": round(base, 4), "n": len(rows)}


# ------------------------------------------------------------------- apply
def _invalidate_all_screeners() -> None:
    """auto_judge can exist twice in one process (package `server.auto_judge`
    and the benchmark's top-level `auto_judge`); stale threshold caches in
    EITHER would poison gating. Invalidate every loaded instance."""
    import sys as _sys
    for name in ("auto_judge", "server.auto_judge"):
        m = _sys.modules.get(name)
        if m is not None and hasattr(m, "invalidate_params"):
            m.invalidate_params()


def gold_gate(params: dict) -> tuple[bool, float]:
    """Run the gold-corpus verdict benchmark UNDER candidate params."""
    import os
    import sys
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "scripts"))
    from . import auto_judge
    old = os.environ.get("W2_SCREENER_PARAMS")
    os.environ["W2_SCREENER_PARAMS"] = json.dumps(params)
    _invalidate_all_screeners()
    try:
        import nlp_benchmark
        res = nlp_benchmark.run_benchmark()
        a = res["components"]["verdicts"]["accuracy"]
        return a >= GOLD_FLOOR, a
    finally:
        if old is None:
            os.environ.pop("W2_SCREENER_PARAMS", None)
        else:
            os.environ["W2_SCREENER_PARAMS"] = old
        _invalidate_all_screeners()


def apply(fitres: dict) -> dict:
    """Gate the fitted params on the gold corpus; persist only if they hold
    the floor. -> {"applied", "gold_accuracy", ...}"""
    ok, gold = gold_gate(fitres["params"])
    out = {"applied": False, "gold_accuracy": gold, **fitres}
    if not ok:
        out["rejected"] = (f"gold verdict accuracy {gold:.1%} under candidate "
                           f"params is below the {GOLD_FLOOR:.0%} floor")
        return out
    from . import auto_judge
    LEARN_DIR.mkdir(parents=True, exist_ok=True)
    PARAMS.write_text(json.dumps(
        {"version": int(time.time()), "fitted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
         "fitted_from_rows": fitres["n"], "history_accuracy": fitres["accuracy"],
         "gold_accuracy": gold, **fitres["params"]}, indent=1, sort_keys=True))
    _invalidate_all_screeners()
    out["applied"] = True
    return out


# ------------------------------------------------- loop 2: finding feedback
FEEDBACK = LEARN_DIR / "feedback.jsonl"


def finding_class(rd: Path, finding_id: str) -> str:
    """(dimension, verdict) class of a finding, from the run's own bundle."""
    try:
        b = json.loads((rd / "sdd-review-bundle.json").read_text())
        for f in b.get("findings") or []:
            if f.get("id") == finding_id:
                return f"d{f.get('dimension')}:{f.get('verdict')}"
    except Exception:
        pass
    return "unknown"


def record_feedback(run_id: str, member, finding_id: str,
                    useful: bool, cls: str) -> None:
    LEARN_DIR.mkdir(parents=True, exist_ok=True)
    with FEEDBACK.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                             "run": run_id, "member": member or "operator",
                             "finding_id": finding_id, "useful": bool(useful),
                             "class": cls}, sort_keys=True) + "\n")


def feedback_weights() -> dict:
    """Beta-mean usefulness per finding class ((ups+1)/(n+2), Laplace) —
    the bandit weight consumers use to order recommendations. Classes never
    drop to zero: every class keeps a floor of exploration."""
    ups: dict = {}
    n: dict = {}
    if FEEDBACK.exists():
        for line in FEEDBACK.read_text().splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            c = r.get("class") or "unknown"
            n[c] = n.get(c, 0) + 1
            ups[c] = ups.get(c, 0) + (1 if r.get("useful") else 0)
    return {c: round((ups.get(c, 0) + 1) / (n[c] + 2), 4) for c in n}
