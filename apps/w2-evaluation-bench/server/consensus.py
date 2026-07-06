"""consensus.py — the deterministic dual-judge consensus engine (v2.0 core).

Pure functions over in-memory scorecards (TR-12): no file I/O, no clock, no
randomness. Identical inputs produce byte-identical records (TR-13): dict keys
are emitted sorted and no timestamps live in the record body.

The three entry points mirror the TRD:

    diff(cards, criteria, sub_max, dims, dim_max)      -> divergence listing
    merge(cards, rulings, ...)                          -> consensus record
    stats(record, dims, dim_max)                        -> agreement statistics

Thresholds, verdict order, and judge names come from contracts (single source
of truth): SUB_DELTA_FRAC (0.20), DIM_DELTA_FRAC (0.10), VERDICT_ORDER
(Present > Partial > Absent), JUDGES.

Conservatism rules (PRD D4, Backend Schema section 6.2):
- a `dissent` verdict resolves to the WEAKER verdict; the anchor kept is the
  anchor of the judge whose verdict survives;
- a `dissent` score resolves to min(a, b);
- NA participates in neither coverage nor agreement denominators; an NA-vs-X
  dissent resolves to the weaker of (Absent, X) — NA never wins a dissent,
  because adopting NA would REMOVE the criterion from the denominators and
  could raise apparent coverage, which is anti-conservative (errata Q-NA);
- a criterion present in one judge's verdicts and absent from the other's is
  treated as an implicit NA on the silent side and is a divergence — coverage
  must never silently depend on which judge remembered to emit a criterion.

Dim-3 RR netting and the Dim-4 floor are applied AFTER the merge, to the
consensus values AND to each judge's own dimension totals (TR-14), from the
lane's release summary and mapping floor carried in packet meta. Judges are
instructed to report RAW sub-scores (the v2.0 pass prompt forbids
self-netting), so the engine applies each adjustment exactly once, in one
place, identically for the three columns (Judge A / Judge B / Consensus).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# contracts lives in the vendored engine; config.py has already extended
# sys.path when the server imports us. For standalone/test use, extend here.
_SCRIPTS = Path(__file__).resolve().parent.parent / "engine" / "evaluate-sdd" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
import contracts  # noqa: E402

JUDGE_A, JUDGE_B = contracts.JUDGES  # ("claude-code", "gemini")

# Weaker-first rank: lower rank = weaker verdict. NA is handled by the
# explicit rules above, never by this rank.
_VERDICT_RANK = {v: i for i, v in enumerate(reversed(contracts.VERDICT_ORDER))}
# e.g. {"Absent": 0, "Partial": 1, "Present": 2}

_NA_ENTRY = {"verdict": "NA", "evidence_anchor": "", "sdd_ref": "",
             "components_present": [], "components_partial": [],
             "components_absent": [], "implicit": True}


# ------------------------------------------------------------------ helpers
def _content_words(text: str) -> set:
    """EXACT replica of evidence_anchor_verify.supports_verdict tokenization:
    lowercase, whitespace-collapse, split, keep punctuation, keep len > 3."""
    t = re.sub(r"\s+", " ", str(text or "").lower()).strip()
    return {w for w in t.split() if len(w) > 3}


def _anchors_equivalent(a: str, b: str) -> bool:
    """Present/Partial anchor pair equivalence (Backend Schema section 6.3):
    equivalent iff they share at least one content word."""
    return bool(_content_words(a) & _content_words(b))


def _weaker(v1: str, v2: str) -> str:
    """The weaker of two non-NA verdicts per contracts.VERDICT_ORDER."""
    return v1 if _VERDICT_RANK[v1] <= _VERDICT_RANK[v2] else v2


def _conservative_verdict(va: str, vb: str) -> str:
    """Dissent resolution: weaker verdict; NA never wins (treated as Absent
    for the comparison, so NA-vs-X resolves to weaker(Absent, X) = Absent
    unless X is itself Absent)."""
    ea = "Absent" if va == "NA" else va
    eb = "Absent" if vb == "NA" else vb
    return _weaker(ea, eb)


def _entry(card: dict, cid: str) -> dict:
    """A judge's verdict entry for a criterion, or the implicit-NA entry."""
    e = (card.get("verdicts") or {}).get(cid)
    return dict(e) if isinstance(e, dict) else dict(_NA_ENTRY)


def _sub_value(card: dict, dim: str, key: str):
    subs = (card.get("sub_scores") or {}).get(dim) or {}
    v = subs.get(key)
    return float(v) if isinstance(v, (int, float)) else None


def sub_item_key(dim: str, key: str) -> str:
    """Reconcile item key for a sub-score divergence (errata Q8)."""
    return f"sub:{dim}:{key}"


def _round1(x: float) -> float:
    return round(float(x) + 0.0, 1)


# ---------------------------------------------------------------------- diff
def diff(cards: dict, criteria: list, sub_max: dict, dims: list,
         dim_max: dict) -> dict:
    """List every divergence between the two judges' scorecards for one
    (lane, dim-group).

    cards:    {judge_name: scorecard} with exactly the two contracts.JUDGES.
    criteria: the calibration slice's applicable_criteria (list of dicts with
              at least "id"); defines the criterion universe.
    sub_max:  {sub_key: max_points} for this dim-group's sub-criteria.
    dims:     the group's dimension keys, e.g. ["1", "2", "3"].
    dim_max:  {dim: max_points}, already integration-heavy-aware.

    Returns {"criteria": {cid: {judge: entry}}, "subs": {item_key: {judge:
    score, "_dim", "_sub_key", "_max"}}, "dim_gaps": {dim: {judge: score}}}
    containing ONLY divergent items, with deterministic (sorted) ordering.
    """
    a, b = cards[JUDGE_A], cards[JUDGE_B]
    out_crit = {}
    ids = [c["id"] for c in criteria]
    # Include any extra criterion a judge emitted beyond the slice: it still
    # needs adjudication rather than silent dropping.
    extra = (set((a.get("verdicts") or {})) | set((b.get("verdicts") or {}))) - set(ids)
    for cid in ids + sorted(extra):
        ea, eb = _entry(a, cid), _entry(b, cid)
        va, vb = ea.get("verdict"), eb.get("verdict")
        if va == "NA" and vb == "NA":
            continue  # agreed-NA; excluded from all denominators
        if va != vb:
            out_crit[cid] = {JUDGE_A: ea, JUDGE_B: eb}
            continue
        if va in ("Present", "Partial") and not _anchors_equivalent(
                ea.get("evidence_anchor"), eb.get("evidence_anchor")):
            out_crit[cid] = {JUDGE_A: ea, JUDGE_B: eb}

    out_subs = {}
    for dim in dims:
        keys = sorted(set(((a.get("sub_scores") or {}).get(dim) or {}))
                      | set(((b.get("sub_scores") or {}).get(dim) or {})))
        for key in keys:
            sa, sb = _sub_value(a, dim, key), _sub_value(b, dim, key)
            if sa is None or sb is None:
                # a missing sub-score is a divergence by construction
                out_subs[sub_item_key(dim, key)] = {
                    JUDGE_A: sa, JUDGE_B: sb, "_dim": dim, "_sub_key": key,
                    "_max": sub_max.get(key)}
                continue
            mx = sub_max.get(key)
            if mx and abs(sa - sb) > contracts.SUB_DELTA_FRAC * float(mx):
                # STRICTLY greater: a delta exactly at 20% of max is agreement
                out_subs[sub_item_key(dim, key)] = {
                    JUDGE_A: sa, JUDGE_B: sb, "_dim": dim, "_sub_key": key,
                    "_max": mx}

    # Dimension-level gaps are informational: after the sub-level merge the
    # 10%-of-max check is re-asserted in merge(); they are never judge-ruled.
    dim_gaps = {}
    for dim in dims:
        da = (a.get("dim_scores") or {}).get(dim)
        db = (b.get("dim_scores") or {}).get(dim)
        if isinstance(da, (int, float)) and isinstance(db, (int, float)):
            if abs(float(da) - float(db)) > contracts.DIM_DELTA_FRAC * float(dim_max[dim]):
                dim_gaps[dim] = {JUDGE_A: float(da), JUDGE_B: float(db)}

    return {"criteria": out_crit, "subs": out_subs, "dim_gaps": dim_gaps}


# --------------------------------------------------------------------- merge
def _apply_criterion_ruling(cid: str, pair: dict, ruling: dict):
    """Resolve one divergent criterion from its reconcile ruling.
    Returns (provenance, consensus_entry, ruling_citation, ruling_rationale,
    dissent_record|None). Raises ValueError on a semantically invalid ruling.
    """
    ea, eb = pair[JUDGE_A], pair[JUDGE_B]
    r = (ruling or {}).get("ruling")
    citation = (ruling or {}).get("citation") or None
    rationale = (ruling or {}).get("rationale") or None

    if r == "adopt_claude":
        return "adopt_claude", _strip(ea), citation, rationale, None
    if r == "adopt_gemini":
        return "adopt_gemini", _strip(eb), citation, rationale, None
    if r == "meet_between":
        va, vb = ea.get("verdict"), eb.get("verdict")
        ranks = sorted(_VERDICT_RANK.get("Absent" if v == "NA" else v, 0)
                       for v in (va, vb))
        value = (ruling or {}).get("value") or {}
        vm = value.get("verdict")
        if vm not in _VERDICT_RANK or not (ranks[0] < _VERDICT_RANK[vm] < ranks[1]):
            raise ValueError(
                f"reconcile ruling for {cid!r}: meet_between verdict {vm!r} does not "
                f"lie strictly between {va!r} and {vb!r}")
        if not citation:
            raise ValueError(f"reconcile ruling for {cid!r}: meet_between requires a citation")
        entry = {"verdict": vm,
                 "evidence_anchor": value.get("evidence_anchor") or citation,
                 "sdd_ref": value.get("sdd_ref") or ea.get("sdd_ref") or eb.get("sdd_ref") or "",
                 "components_present": value.get("components_present", []),
                 "components_partial": value.get("components_partial", []),
                 "components_absent": value.get("components_absent", [])}
        return "meet_between", entry, citation, rationale, None
    if r == "dissent":
        vc = _conservative_verdict(ea.get("verdict"), eb.get("verdict"))
        keeper = ea if ("Absent" if ea.get("verdict") == "NA" else ea.get("verdict")) == vc else eb
        entry = _strip(keeper)
        entry["verdict"] = vc
        if vc == "Absent" and not entry.get("evidence_anchor"):
            entry["evidence_anchor"] = "topic absent from SDD"
        dissent = {"criterion_id": cid,
                   JUDGE_A: _strip(ea), JUDGE_B: _strip(eb),
                   "conservative_resolution": dict(entry),
                   "why_unresolved": rationale or "judges could not be reconciled on the cited evidence"}
        return "dissent", entry, citation, rationale, dissent
    raise ValueError(f"reconcile ruling for {cid!r}: unknown ruling {r!r}")


def _strip(entry: dict) -> dict:
    return {"verdict": entry.get("verdict"),
            "evidence_anchor": entry.get("evidence_anchor", ""),
            "sdd_ref": entry.get("sdd_ref", ""),
            "components_present": entry.get("components_present", []),
            "components_partial": entry.get("components_partial", []),
            "components_absent": entry.get("components_absent", [])}


def _apply_sub_ruling(item_key: str, sa: float, sb: float, mx: float,
                      ruling: dict):
    """Resolve one divergent sub-score. Returns (provenance, value,
    dissent_record|None). Raises ValueError on invalid rulings."""
    r = (ruling or {}).get("ruling")
    lo, hi = sorted([x for x in (sa, sb) if x is not None]) if None not in (sa, sb) \
        else (None, None)
    if r == "adopt_claude":
        if sa is None:
            raise ValueError(f"{item_key}: adopt_claude but Judge A has no score")
        return "adopt_claude", float(sa), None
    if r == "adopt_gemini":
        if sb is None:
            raise ValueError(f"{item_key}: adopt_gemini but Judge B has no score")
        return "adopt_gemini", float(sb), None
    if r == "meet_between":
        v = (ruling or {}).get("value")
        if isinstance(v, dict):
            v = v.get("score")
        if not isinstance(v, (int, float)):
            raise ValueError(f"{item_key}: meet_between requires a numeric value")
        if lo is None or not (lo <= float(v) <= hi):
            raise ValueError(
                f"{item_key}: meet_between value {v} outside the judges' range [{lo}, {hi}]")
        if not (ruling or {}).get("citation"):
            raise ValueError(f"{item_key}: meet_between requires a citation")
        return "meet_between", float(v), None
    if r == "dissent":
        vals = [x for x in (sa, sb) if x is not None]
        value = min(vals) if vals else 0.0
        dissent = {"sub_key": item_key,
                   JUDGE_A: sa, JUDGE_B: sb,
                   "conservative_resolution": value,
                   "why_unresolved": (ruling or {}).get("rationale")
                   or "judges could not be reconciled on the cited evidence"}
        return "dissent", float(value), dissent
    raise ValueError(f"{item_key}: unknown ruling {r!r}")


def merge(cards: dict, rulings: dict | None, *, criteria: list, sub_max: dict,
          dims: list, dim_max: dict, lane: str, dim_group: str,
          rr_capped_total: float = 0.0, floor_cap=None) -> dict:
    """Merge two scorecards (+ reconcile rulings for their divergences) into
    the consensus record for one (lane, dim-group). Backend Schema section 6.

    rulings: {item_key: ruling_dict} from the reconcile packet result, or None
    when diff() found no divergences. Every divergent item MUST have a ruling;
    a missing ruling raises ValueError (the orchestrator reopens the packet).

    Dim-3 netting (rr_capped_total, a value <= 0) and the Dim-4 floor
    (floor_cap or None) are applied here, after the merge, to consensus AND
    per-judge dimension totals alike (TR-14) — judges report raw scores.
    """
    a, b = cards[JUDGE_A], cards[JUDGE_B]
    rulings = rulings or {}
    d = diff(cards, criteria, sub_max, dims, dim_max)

    items, dissents = {}, []
    ids = [c["id"] for c in criteria]
    extra = (set((a.get("verdicts") or {})) | set((b.get("verdicts") or {}))) - set(ids)
    for cid in ids + sorted(extra):
        ea, eb = _entry(a, cid), _entry(b, cid)
        va, vb = ea.get("verdict"), eb.get("verdict")
        if va == "NA" and vb == "NA":
            items[cid] = {"provenance": "agreed", "consensus": _strip(ea),
                          "judge_entries": None,
                          "ruling_citation": None, "ruling_rationale": None}
            continue
        if cid not in d["criteria"]:
            # agreed: Judge A's anchor kept; both retained when texts differ
            keep_both = (ea.get("evidence_anchor") or "") != (eb.get("evidence_anchor") or "")
            items[cid] = {"provenance": "agreed", "consensus": _strip(ea),
                          "judge_entries": ({JUDGE_A: _strip(ea), JUDGE_B: _strip(eb)}
                                            if keep_both else None),
                          "ruling_citation": None, "ruling_rationale": None}
            continue
        if cid not in rulings:
            raise ValueError(f"divergent criterion {cid!r} has no reconcile ruling")
        prov, entry, citation, rationale, dissent = _apply_criterion_ruling(
            cid, d["criteria"][cid], rulings[cid])
        items[cid] = {"provenance": prov, "consensus": entry,
                      "judge_entries": {JUDGE_A: _strip(ea), JUDGE_B: _strip(eb)},
                      "ruling_citation": citation, "ruling_rationale": rationale}
        if dissent:
            dissents.append(dissent)

    # ---- sub-scores: three-key objects with provenance
    sub_out = {}
    for dim in dims:
        keys = sorted(set(((a.get("sub_scores") or {}).get(dim) or {}))
                      | set(((b.get("sub_scores") or {}).get(dim) or {})))
        dim_subs = {}
        for key in keys:
            sa, sb = _sub_value(a, dim, key), _sub_value(b, dim, key)
            ik = sub_item_key(dim, key)
            if ik in d["subs"]:
                if ik not in rulings:
                    raise ValueError(f"divergent sub-score {ik!r} has no reconcile ruling")
                prov, val, dissent = _apply_sub_ruling(
                    ik, sa, sb, sub_max.get(key) or 0.0, rulings[ik])
                if dissent:
                    dissents.append(dissent)
            else:
                prov = "agreed"
                vals = [x for x in (sa, sb) if x is not None]
                val = sum(vals) / len(vals) if vals else 0.0
            dim_subs[key] = {JUDGE_A: sa, JUDGE_B: sb,
                             "consensus": _round1(val), "provenance": prov}
        sub_out[dim] = dim_subs

    # ---- dimension totals: recompute bottom-up, then net/floor (TR-14)
    def _dim_total(source: str, dim: str) -> float:
        if source == "consensus":
            raw = sum(v["consensus"] for v in sub_out[dim].values())
        else:
            raw = sum(v[source] or 0.0 for v in sub_out[dim].values())
        if dim == "3" and rr_capped_total:
            raw = max(0.0, raw + float(rr_capped_total))  # rr_capped_total <= 0
        if dim == "4" and floor_cap is not None:
            raw = min(raw, float(floor_cap))
        return _round1(raw)

    dim_out = {}
    for dim in dims:
        dim_out[dim] = {JUDGE_A: _dim_total(JUDGE_A, dim),
                        JUDGE_B: _dim_total(JUDGE_B, dim),
                        "consensus": _dim_total("consensus", dim)}
        # Defensive re-assertion (Backend Schema section 6.2.3): consensus must
        # sit within the judges' post-adjustment envelope, else the merge itself
        # is wrong — this is a code bug, not a judge disagreement.
        lo = min(dim_out[dim][JUDGE_A], dim_out[dim][JUDGE_B])
        hi = max(dim_out[dim][JUDGE_A], dim_out[dim][JUDGE_B])
        if not (lo - 1e-6 <= dim_out[dim]["consensus"] <= hi + 1e-6):
            raise AssertionError(
                f"consensus dim {dim} total {dim_out[dim]['consensus']} escaped the judge "
                f"envelope [{lo}, {hi}] after merge — merge invariant violated")

    record = {"lane": lane, "dim_group": dim_group,
              "judges": {JUDGE_A: f"scorecards/{lane}_{dim_group}_{JUDGE_A}.json",
                         JUDGE_B: f"scorecards/{lane}_{dim_group}_{JUDGE_B}.json"},
              "items": items, "sub_scores": sub_out, "dim_scores": dim_out,
              "dissents": dissents}
    record["stats"] = stats(record, dims, dim_max)
    return record


# --------------------------------------------------------------------- stats
def stats(record: dict, dims: list, dim_max: dict) -> dict:
    """Agreement statistics per Backend Schema section 6.5, computed ONCE here
    (TR-21) and consumed by bundle, checkpoint, lift, and report.

    - verdict_agreement_rate: matched verdicts / non-NA criteria (per dim +
      overall). "Matched" means the two judges' original verdicts agreed
      (provenance 'agreed' on a non-NA item).
    - score_concordance per dim: 1 - |dimA - dimB| / dim_max, on the
      post-adjustment judge totals; overall = dim_max-weighted mean (errata Q2).
    - agreement_overall = 0.5 * verdict_agreement_rate + 0.5 * score_concordance.
    """
    per_dim_matched = {d: 0 for d in dims}
    per_dim_total = {d: 0 for d in dims}
    divergence_count = 0
    for cid, item in (record.get("items") or {}).items():
        cons = item.get("consensus") or {}
        prov = item.get("provenance")
        dim = cid.split(".")[0][0] if cid else ""
        if dim not in per_dim_total:
            continue
        if prov == "agreed" and cons.get("verdict") == "NA":
            continue  # agreed-NA: out of every denominator
        per_dim_total[dim] += 1
        if prov == "agreed":
            per_dim_matched[dim] += 1
        else:
            divergence_count += 1
    divergence_count += sum(
        1 for dim in dims for v in (record.get("sub_scores") or {}).get(dim, {}).values()
        if v.get("provenance") != "agreed")

    rate_per_dim = {d: (per_dim_matched[d] / per_dim_total[d]) if per_dim_total[d] else None
                    for d in dims}
    tot = sum(per_dim_total.values())
    rate_overall = (sum(per_dim_matched.values()) / tot) if tot else None

    conc_per_dim = {}
    for d in dims:
        ds = (record.get("dim_scores") or {}).get(d) or {}
        da, db = ds.get(JUDGE_A), ds.get(JUDGE_B)
        mx = float(dim_max[d])
        conc_per_dim[d] = (max(0.0, 1.0 - abs(da - db) / mx)
                           if isinstance(da, (int, float)) and isinstance(db, (int, float)) and mx
                           else None)
    weights = {d: float(dim_max[d]) for d in dims if conc_per_dim[d] is not None}
    wsum = sum(weights.values())
    conc_overall = (sum(conc_per_dim[d] * w for d, w in weights.items()) / wsum
                    if wsum else None)

    dissent_count = len(record.get("dissents") or [])
    agreement_overall = (0.5 * rate_overall + 0.5 * conc_overall
                         if rate_overall is not None and conc_overall is not None
                         else rate_overall if rate_overall is not None else conc_overall)
    return {
        "verdict_agreement_rate": _r3(rate_overall),
        "verdict_agreement_rate_per_dim": {d: _r3(v) for d, v in rate_per_dim.items()},
        "score_concordance": _r3(conc_overall),
        "score_concordance_per_dim": {d: _r3(v) for d, v in conc_per_dim.items()},
        "divergence_count": divergence_count,
        "dissent_count": dissent_count,
        "agreement_overall": _r3(agreement_overall),
        "non_na_criteria": tot,
        "reliability_label": reliability_label(agreement_overall),
    }


def _r3(v):
    return round(v, 3) if isinstance(v, (int, float)) else None


def reliability_label(overall) -> str:
    """The exact section-6.5 vocabulary; also rendered by the console."""
    if not isinstance(overall, (int, float)):
        return ""
    if overall >= 0.85:
        return "strong cross-model concurrence"
    if overall >= 0.70:
        return "moderate — read the annex"
    return "weak — treat scores as contested"


def merge_lane_stats(group_stats: list) -> dict:
    """Combine the two dim-group stats of one lane (criteria-count weighted for
    rates; concordance already dim_max-weighted per group, re-weighted by the
    groups' dim_max sums). Deterministic; used by judge_accumulate."""
    tot = sum(s.get("non_na_criteria") or 0 for s in group_stats)
    rate = (sum((s.get("verdict_agreement_rate") or 0.0) * (s.get("non_na_criteria") or 0)
                for s in group_stats) / tot) if tot else None
    per_dim_rate, per_dim_conc = {}, {}
    for s in group_stats:
        per_dim_rate.update(s.get("verdict_agreement_rate_per_dim") or {})
        per_dim_conc.update(s.get("score_concordance_per_dim") or {})
    weights = {d: contracts.dim_max(int(d)) for d, v in per_dim_conc.items() if v is not None}
    wsum = sum(weights.values())
    conc = (sum(per_dim_conc[d] * w for d, w in weights.items()) / wsum) if wsum else None
    divergences = sum(s.get("divergence_count") or 0 for s in group_stats)
    dissents = sum(s.get("dissent_count") or 0 for s in group_stats)
    overall = (0.5 * rate + 0.5 * conc if rate is not None and conc is not None
               else rate if rate is not None else conc)
    return {"verdict_agreement_rate": _r3(rate),
            "verdict_agreement_rate_per_dim": per_dim_rate,
            "score_concordance": _r3(conc),
            "score_concordance_per_dim": per_dim_conc,
            "divergence_count": divergences, "dissent_count": dissents,
            "agreement_overall": _r3(overall), "non_na_criteria": tot,
            "reliability_label": reliability_label(overall)}


def to_json(record: dict) -> str:
    """Canonical serialization: sorted keys, stable separators (TR-13)."""
    return json.dumps(record, indent=2, sort_keys=True)
