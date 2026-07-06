#!/usr/bin/env python3
"""pass_correlation.py  (Tier 1 — estimate ρ across the five scoring passes)

The five passes are repeated measurements of each dimension's score. Their
information content depends on how CORRELATED they are: five passes that move
together carry far less than five independent ones. This module estimates that
correlation directly from the five-pass arrays the score sheet already stores,
using the one-way random-effects intraclass correlation coefficient (ICC(1)),
and converts it into Kish's design effect and an effective sample size.

ICC(1) is the standard intra-rater-reliability statistic (Koo & Li 2016;
Rating Roulette, EMNLP 2025). It is exactly the right object here: it answers
"what fraction of the total variance is between-dimension (true signal) vs
within-dimension across passes (pass noise)", which is precisely the ρ that
governs Var(mean) = (σ²/n)·[1 + (n−1)ρ].

Design effect:  deff = 1 + (n−1)·ρ
Effective n:    n_eff = n / deff
Reported-CI understatement factor: sqrt(deff)   (true SE / naive SE)

All deterministic. No external deps beyond the stdlib.
"""
from __future__ import annotations
import statistics
from typing import Optional


def icc1(groups: list[list[float]]) -> Optional[float]:
    """One-way random-effects ICC(1) over `groups`, where each group is the set of
    per-pass scores for one dimension. Returns ρ̂ in [0,1] (clamped), or None if
    there isn't enough data. ICC(1) = (MSB − MSW) / (MSB + (k−1)·MSW), with k the
    (mean) group size, MSB between-group mean square, MSW within-group mean square.

    Intuition: high ICC ⇒ the passes for a given dimension cluster tightly relative
    to differences BETWEEN dimensions ⇒ passes are highly correlated ⇒ small n_eff.
    """
    groups = [g for g in groups if g and len(g) >= 2]
    if len(groups) < 2:
        return None
    k_sizes = [len(g) for g in groups]
    N = sum(k_sizes)
    a = len(groups)                      # number of groups (dimensions)
    grand = sum(sum(g) for g in groups) / N
    # Between-group sum of squares
    ssb = sum(len(g) * (statistics.mean(g) - grand) ** 2 for g in groups)
    # Within-group sum of squares
    ssw = sum(sum((x - statistics.mean(g)) ** 2 for x in g) for g in groups)
    df_b = a - 1
    df_w = N - a
    if df_b <= 0 or df_w <= 0:
        return None
    msb = ssb / df_b
    msw = ssw / df_w
    # mean group size (k0) — for balanced designs this is just k
    if a > 1:
        k0 = (N - sum(s * s for s in k_sizes) / N) / (a - 1)
    else:
        k0 = statistics.mean(k_sizes)
    denom = msb + (k0 - 1) * msw
    if denom == 0:
        return 0.0
    icc = (msb - msw) / denom
    # ICC can go slightly negative from sampling noise; clamp to [0,1].
    return max(0.0, min(1.0, icc))


def design_effect(rho: float, n: int) -> float:
    return 1.0 + (n - 1) * max(0.0, rho)


def effective_n(rho: float, n: int) -> float:
    deff = design_effect(rho, n)
    return n / deff if deff > 0 else float(n)


def assess_pass_correlation(per_dim_runs: dict, n_passes: int = 5) -> Optional[dict]:
    """Estimate ρ̂ across passes from the score sheet's per-dimension five-pass
    arrays (per_dim_runs maps dim->[p1..p5]). Returns ρ̂, design effect, n_eff,
    the SE-understatement factor, and a plain-language reliability label.

    Also runs a DEGENERATE-VARIANCE check: if the passes are (near-)identical across
    every dimension, that is the statistical signature of passes that were NOT
    blinded from each other (they anchored/copied) or were scored too vaguely to
    differ. Real independent passes essentially never produce zero spread on every
    dimension. When detected, the result carries blinding_warning=True so the report
    refuses to present the "five passes" spread as genuine reliability."""
    groups = [list(map(float, v)) for v in (per_dim_runs or {}).values()
              if isinstance(v, (list, tuple)) and len(v) >= 2]
    rho = icc1(groups)
    if rho is None:
        return None
    counts = [len(g) for g in groups]
    n = max(set(counts), key=counts.count) if counts else n_passes
    deff = design_effect(rho, n)
    n_eff = effective_n(rho, n)
    se_factor = deff ** 0.5

    # --- degenerate-variance / blinding-failure detector ---
    import statistics as _st
    spreads = [(max(g) - min(g)) for g in groups]
    within_sd = [(_st.stdev(g) if len(g) >= 2 else 0.0) for g in groups]
    n_zero = sum(1 for s in spreads if s == 0.0)
    frac_zero = n_zero / len(groups) if groups else 0.0
    mean_within_sd = (sum(within_sd) / len(within_sd)) if within_sd else 0.0
    # All-or-almost-all dimensions with zero spread => passes are not independent.
    blinding_warning = frac_zero >= 0.8 or mean_within_sd < 0.05
    blinding_note = None
    if blinding_warning:
        blinding_note = (
            f"DEGENERATE PASS VARIANCE: {n_zero}/{len(groups)} dimensions show zero "
            f"spread across the five passes (mean within-pass SD={mean_within_sd:.3f}). "
            f"Independent passes essentially never do this. The passes were most likely "
            f"NOT blinded from each other (they anchored on or copied an earlier pass), "
            f"or were scored too vaguely to differ. The five-pass spread is therefore "
            f"NOT evidence of reliability for this run — treat the score as a single "
            f"measurement and re-run with each pass scored cold (see pass_plan "
            f"inter_pass_blinding).")

    if rho < 0.2:
        label = "passes weakly correlated — five passes carry close to five independent measurements"
    elif rho < 0.5:
        label = "passes moderately correlated — effective information noticeably below five passes"
    elif rho < 0.8:
        label = "passes strongly correlated — five passes carry roughly one-to-two independent measurements"
    else:
        label = "passes very strongly correlated — five passes carry barely more than one independent measurement"
    return {
        "schema": "pass-correlation/v1",
        "n_passes": n,
        "icc_rho_hat": round(rho, 3),
        "design_effect": round(deff, 2),
        "effective_n_passes": round(n_eff, 2),
        "reported_se_understatement_factor": round(se_factor, 2),
        "reliability_label": label,
        "blinding_warning": blinding_warning,
        "blinding_note": blinding_note,
        "dimensions_zero_spread": n_zero,
        "mean_within_pass_sd": round(mean_within_sd, 3),
        "method": ("ICC(1) one-way random-effects over the per-dimension five-pass "
                   "arrays; design effect = 1+(n-1)·ρ̂; n_eff = n/design_effect. "
                   "ρ̂ measures how correlated the passes are — it does NOT lower "
                   "the correlation, it makes the reported uncertainty honest. The "
                   "blinding_warning flags degenerate (near-identical) passes that "
                   "indicate the passes were not independent."),
    }


if __name__ == "__main__":
    # tiny self-demo
    independentish = {"1": [70, 62, 78, 55, 81], "2": [60, 90, 45, 72, 66],
                      "3": [88, 50, 70, 63, 79], "4": [55, 75, 60, 85, 48]}
    correlated = {"1": [80, 80, 81, 79, 80], "2": [60, 61, 60, 59, 60],
                  "3": [70, 70, 71, 70, 69], "4": [55, 55, 54, 56, 55]}
    import json
    print("near-independent:", json.dumps(assess_pass_correlation(independentish)))
    print("highly-correlated:", json.dumps(assess_pass_correlation(correlated)))
