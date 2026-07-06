#!/usr/bin/env python3
"""stability.py — runtime gate/band stability helper.

Pure, deterministic recompute (no model calls, no network): given a lane's
per-dimension means, does each dimension's gate verdict and quality band survive
a +/- N percentage-point change to the hand-set thresholds? The diagnostic
report uses this to state its own robustness ("verdict stable" vs "knife-edge").

All band/gate boundary numbers are single-sourced from contracts.py (rubric s.3
bands, s.8 gate). This module is imported by the report builder
(diagnostic_report_populate.py) and re-exported by the score-sensitivity QA
harness, so the production path carries no dependency on the QA folder.
"""

from __future__ import annotations

import contracts


def _band_boundaries():
    """Ascending band-boundary percentages (rubric s.3, four-band): 65, 70, 80."""
    return sorted(f for f, _ in contracts.BAND_SCALE if f > 0)


def _gate_boundaries():
    """Ascending gate-boundary percentages (rubric s.8, four-band): 65, 70, 80."""
    return sorted([contracts.GATE_MARGINAL_FRACTION * 100.0,
                   contracts.GATE_GOOD_FRACTION * 100.0,
                   contracts.GATE_PASS_FRACTION * 100.0])


def _nearest_margin(pct, boundaries):
    """Smallest distance (pp) from pct to any boundary."""
    return min(abs(pct - b) for b in boundaries)


def _stability_phrase(stable, perturbations):
    p = max(perturbations)
    g = stable[p]["gate"]; b = stable[p]["band"]
    if g and b:
        return f"Verdict stable: no dimension's gate or band flips under a +/-{p:g}pp threshold change."
    parts = []
    if not g:
        parts.append("at least one gate verdict")
    if not b:
        parts.append("at least one quality band")
    return (f"Knife-edge: {', and '.join(parts)} flips under a +/-{p:g}pp threshold change "
            f"- treat the affected dimension(s) as borderline.")


def gate_band_stability(per_dim_means: dict, integration_heavy: bool = False,
                        perturbations=(5.0, 10.0)) -> dict:
    """per_dim_means: {dim(str|int): mean}. perturbations are in percentage points
    of max (a +/-10% threshold move ~ 8 pp at the 80% gate; we use pp directly so
    the same margin compares across band and gate)."""
    band_bnds = _band_boundaries()
    gate_bnds = _gate_boundaries()
    dims = []
    worst_gate_margin = None
    worst_band_margin = None
    for d in range(1, 8):
        m = per_dim_means.get(str(d), per_dim_means.get(d))
        if not isinstance(m, (int, float)):
            continue
        mx = contracts.dim_max(d, integration_heavy)
        pct = 100.0 * m / mx
        gate_margin = _nearest_margin(pct, gate_bnds)
        band_margin = _nearest_margin(pct, band_bnds)
        flips = {p: {"gate": gate_margin <= p, "band": band_margin <= p} for p in perturbations}
        dims.append({
            "dim": d, "pct": round(pct, 1),
            "gate": contracts.gate_for_pct(pct),
            "band": contracts.band_for_pct(pct),
            "gate_margin_pp": round(gate_margin, 1),
            "band_margin_pp": round(band_margin, 1),
            "knife_edge": flips,
        })
        worst_gate_margin = gate_margin if worst_gate_margin is None else min(worst_gate_margin, gate_margin)
        worst_band_margin = band_margin if worst_band_margin is None else min(worst_band_margin, band_margin)

    stable = {p: {"gate": all(not dd["knife_edge"][p]["gate"] for dd in dims),
                  "band": all(not dd["knife_edge"][p]["band"] for dd in dims)}
              for p in perturbations}
    return {
        "per_dim": dims,
        "worst_gate_margin_pp": None if worst_gate_margin is None else round(worst_gate_margin, 1),
        "worst_band_margin_pp": None if worst_band_margin is None else round(worst_band_margin, 1),
        "stable_under": stable,
        "summary": _stability_phrase(stable, perturbations),
    }
