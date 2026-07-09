#!/usr/bin/env python3
"""
pass_plan.py (v4.6) — make the five scoring passes genuinely independent, and
challenge every Present verdict before it counts.

Two reliability problems this fixes, both without any extra model API:

1. CORRELATED PASSES. Five passes generated in one context, in the same criterion
   order, with the same framing, are statistically correlated, so the pass
   standard deviation is biased low and the variance flag (stddev > 1.0) rarely
   fires. The "we ran it five times" reliability claim is then partly an artefact.
   pass_plan() decorrelates the passes deterministically (reproducible from the
   run_id): each pass gets a different criterion ORDER, a counterbalanced LANE
   order (so Output A is not always scored first — removing position/anchoring
   bias), and a rotating grader FRAMING. Same evidence, genuinely different paths
   to the verdict, so the spread across passes measures something real.

2. SELF-AGREEMENT BIAS. A single mind tends to agree with its own first reading.
   challenge_targets() selects every Present verdict (and any non-unanimous
   criterion) for an adversarial re-read whose explicit job is to argue the
   weaker verdict from the same evidence; verdict_stability() then reports which
   verdicts survived and which flipped. A Present that survives its own strongest
   counter-argument is far stronger than one taken at first sight.

Deterministic and seeded — the plan and the challenge set are reproducible for a
given run, the same reproducibility property the frozen calibration gives scores.
"""
from __future__ import annotations

import hashlib

N_PASSES = 5
FRAMINGS = ("neutral", "strict", "literal", "skeptical", "charitable")


def _seed_int(*parts) -> int:
    h = hashlib.sha256("::".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return int(h[:16], 16)


def _deterministic_permutation(items, seed: int):
    """Fisher-Yates with a seeded LCG — no global random state, fully reproducible."""
    arr = list(items)
    state = seed or 1
    for i in range(len(arr) - 1, 0, -1):
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        j = state % (i + 1)
        arr[i], arr[j] = arr[j], arr[i]
    return arr


def pass_plan(run_id: str, criteria_ids, n_passes: int = N_PASSES) -> list[dict]:
    """Return the decorrelation plan: one entry per pass with a distinct criterion
    order, a counterbalanced lane-first, a grader framing, and an explicit
    INTER-PASS BLINDING instruction.

    lane_first alternates A,B,A,B,A so neither lane is consistently scored first.
    criterion_order is a distinct deterministic permutation per pass.
    framing rotates through FRAMINGS so passes are not identical re-reads.

    inter_pass_blinding is the load-bearing addition (v4.3 audit): reordering and
    reframing only decorrelate the SURFACE of a pass. If every pass is generated in
    one context where it can see the earlier passes' scores, the passes anchor on
    each other, variance collapses toward zero, and the measured ICC climbs toward
    1 — the "five passes" reliability claim becomes an artefact. Each pass must
    therefore be scored COLD: re-read the SDD from scratch, with NO sight of any
    prior pass's scores, reasoning, or verdicts. This is the strongest independence
    achievable from a single model; it removes the anchoring correlation (it cannot
    remove the model's shared systematic bias — only a different model family does
    that, see pass_correlation.py).
    """
    ids = list(criteria_ids)
    plan = []
    for p in range(n_passes):
        order = _deterministic_permutation(ids, _seed_int(run_id, "order", p))
        plan.append({
            "pass": p + 1,
            "lane_first": "A" if p % 2 == 0 else "B",
            "framing": FRAMINGS[p % len(FRAMINGS)],
            "criterion_order": order,
            "inter_pass_blinding": (
                f"Score pass {p + 1} COLD. Re-read the SDD from scratch. Do NOT look "
                f"at, recall, or reconcile with any score, verdict, or reasoning from "
                f"passes 1..{p} — they are blinded from you. Reaching the same number "
                f"as a prior pass is fine only if the evidence independently leads "
                f"there; never copy or anchor."),
        })
    return plan


def lane_order_is_counterbalanced(plan) -> bool:
    """True iff neither lane is scored first in every pass (anchoring guard)."""
    firsts = [e["lane_first"] for e in plan]
    return "A" in firsts and "B" in firsts


def challenge_targets(verdicts_by_criterion: dict, critical_floor_ids=None) -> list[str]:
    """Adversarial self-check selection — BOUNDED for context safety (v4.1 QA).

    The heaviest scoring sub-batch (Dims 1-3) carries ~56 criteria at five passes,
    so challenging *every* Present verdict inline could push that single response
    past the context-budget guard. The challenge is therefore scoped to the
    highest-value, bounded set:
      - every **critical-floor** criterion whose verdict is Present (a wrong
        Present here masks a critical gap — the costliest error), and
      - every criterion whose five passes are **not unanimous** (genuine
        uncertainty the passes already surfaced).

    Pass `critical_floor_ids` (from the ZMS register `critical_floor_ids`) to get
    the bounded set. If it is omitted, the function falls back to the unbounded
    set (every Present + non-unanimous) for backward compatibility, but callers in
    the scoring loop MUST pass it so the per-sub-batch challenge count stays small.
    """
    cf = set(critical_floor_ids or [])
    targets = []
    for cid, passes in verdicts_by_criterion.items():
        vals = [v for v in (passes if isinstance(passes, list) else [passes]) if v]
        if not vals:
            continue
        majority = max(set(vals), key=vals.count)
        not_unanimous = len(set(vals)) > 1
        if not_unanimous:
            targets.append(cid)
        elif majority == "Present" and (cid in cf if critical_floor_ids is not None else True):
            targets.append(cid)
    return targets


def verdict_stability(verdicts_by_criterion: dict, challenge_results: dict | None = None,
                      critical_floor_ids=None) -> dict:
    """Summarise pass agreement and adversarial-challenge outcomes.

    verdicts_by_criterion: {criterion_id: [v1..vn]}
    challenge_results: optional {criterion_id: post_challenge_verdict} from the
        adversarial re-read. A target whose post-challenge verdict differs from its
        pre-challenge majority is a FLIP and is surfaced (the original verdict did
        not survive its counter-argument).
    """
    challenge_results = challenge_results or {}
    unstable, flips = [], []
    for cid, passes in verdicts_by_criterion.items():
        vals = [v for v in (passes if isinstance(passes, list) else [passes]) if v]
        if not vals:
            continue
        majority = max(set(vals), key=vals.count)
        if len(set(vals)) > 1:
            unstable.append({"criterion_id": cid, "passes": vals, "majority": majority})
        if cid in challenge_results and challenge_results[cid] != majority:
            flips.append({"criterion_id": cid, "before": majority,
                          "after": challenge_results[cid]})
    targets = challenge_targets(verdicts_by_criterion, critical_floor_ids)
    return {
        "n_criteria": len(verdicts_by_criterion),
        "n_unstable_passes": len(unstable),
        "unstable": unstable,
        "challenge_targets": targets,
        "n_challenge_targets": len(targets),
        "n_flips_after_challenge": len(flips),
        "flips_after_challenge": flips,
        "all_challenged_held": (len(flips) == 0) if challenge_results else None,
    }


# --------------------------------------------------------------------------
# Self-test (CI): determinism, decorrelation, counterbalancing, challenge logic.
# --------------------------------------------------------------------------
def _selftest() -> int:
    fails = 0

    def check(name, cond, detail=""):
        nonlocal fails
        print(f"  {'PASS' if cond else 'FAIL'}: {name}" + (f"  [{detail}]" if not cond and detail else ""))
        if not cond:
            fails += 1

    crit = [f"C{i:02d}" for i in range(1, 21)]
    p1 = pass_plan("RUN-123", crit)
    p2 = pass_plan("RUN-123", crit)
    check("plan is deterministic for a run_id", p1 == p2)
    check("different run_id -> different plan", pass_plan("RUN-999", crit) != p1)
    check("five passes", len(p1) == 5)
    # every pass order is a true permutation (nothing dropped or duplicated)
    check("each pass order is a permutation of all criteria",
          all(sorted(e["criterion_order"]) == sorted(crit) for e in p1))
    # passes are decorrelated: no two passes share the same order
    orders = [tuple(e["criterion_order"]) for e in p1]
    check("criterion orders differ across passes", len(set(orders)) == 5)
    # lane order counterbalanced
    check("lane order is counterbalanced (A and B both go first)",
          lane_order_is_counterbalanced(p1))
    check("framings rotate (>=3 distinct across 5 passes)",
          len({e["framing"] for e in p1}) >= 3)

    # adversarial self-check selection + stability (BOUNDED, v4.1 QA)
    verdicts = {
        "CF1": ["Present", "Present", "Present", "Present", "Present"],  # critical-floor Present -> challenge
        "P1":  ["Present", "Present", "Present", "Present", "Present"],  # non-critical Present -> NOT challenged (bounded)
        "B":   ["Partial", "Partial", "Present", "Partial", "Partial"],  # non-unanimous -> challenge
        "C":   ["Absent", "Absent", "Absent", "Absent", "Absent"],       # unanimous Absent -> no challenge
    }
    cf_ids = {"CF1"}
    targets = challenge_targets(verdicts, critical_floor_ids=cf_ids)
    check("critical-floor Present is challenged", "CF1" in targets)
    check("non-critical-floor Present is NOT challenged when bounded", "P1" not in targets)
    check("non-unanimous verdict is challenged", "B" in targets)
    check("unanimous Absent is not challenged", "C" not in targets)
    check("bounded target count is small", len(targets) <= 3, f"{len(targets)} targets")
    # backward-compat: without critical_floor_ids, all Present are challenged
    unb = challenge_targets(verdicts)
    check("unbounded fallback challenges all Present", "P1" in unb and "CF1" in unb)

    # a critical-floor Present that flips under challenge is surfaced
    stab = verdict_stability(verdicts, challenge_results={"CF1": "Partial", "B": "Partial"},
                             critical_floor_ids=cf_ids)
    check("flip after challenge is surfaced", stab["n_flips_after_challenge"] == 1
          and stab["flips_after_challenge"][0]["criterion_id"] == "CF1")
    check("all_challenged_held is False when a verdict flipped", stab["all_challenged_held"] is False)
    stab2 = verdict_stability(verdicts, challenge_results={"CF1": "Present", "B": "Partial"},
                              critical_floor_ids=cf_ids)
    check("all_challenged_held is True when nothing flips", stab2["all_challenged_held"] is True)

    total = 15
    passed = total - fails
    print(f"\nPass-plan / adversarial self-check: {passed}/{total} passed (rate {passed/total:.2f})")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(_selftest())
