#!/usr/bin/env python3
"""NLP accuracy benchmark: measures every pre-intelligence component against
the hand-labeled gold corpus (tests/gold_corpus.py) and holds the layer to
the 95% bar.

Each gold label is one graded instance; a component's accuracy is the share
of its instances that pass. The corpus is deliberately adversarial (plural
mechanisms, plain-English uses of Salesforce words, paraphrased injections,
hyphenated modality lookalikes), so these numbers measure the layer where it
is most likely to be wrong — not where it is easy.

Usage:
    python3 scripts/nlp_benchmark.py            # table + verdict, exit 1 if <95%
    python3 scripts/nlp_benchmark.py --json     # machine-readable results

Importable: run_benchmark() returns the full result dict; the CI test
(tests/test_nlp_accuracy.py) enforces the same thresholds on every run.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine" / "evaluate-sdd" / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "server"))

import gold_corpus as G  # noqa: E402
from nlp.doc_model import build_doc_model  # noqa: E402
from nlp.evidence_locator import (anchor_relevance, locate_candidates,  # noqa: E402
                                  traceability_matrix)
from nlp.guardrail_lint import blinding_scan, injection_lint  # noqa: E402
from nlp.lexicon import find_mechanisms  # noqa: E402
from nlp.release_support import enrich_queries, review_evidence  # noqa: E402
from nlp.requirements_registry import extract_requirements  # noqa: E402

THRESHOLD = 0.95


def _inst(component: str, check: str, ok: bool, detail: str = "") -> dict:
    return {"component": component, "check": check, "pass": bool(ok),
            "detail": detail}


# ---------------------------------------------------------------- graders
def grade_requirements() -> list[dict]:
    out = []
    reqs = extract_requirements(G.GOLD_BRD)["requirements"]
    ids = {r["id"] for r in reqs if not r["id"].startswith("M-")}
    for rid in sorted(G.GOLD_BRD_IDS):
        out.append(_inst("requirements", f"extracts {rid}", rid in ids))
    for rid in sorted(G.GOLD_BRD_FORBIDDEN_IDS):
        out.append(_inst("requirements", f"rejects {rid}", rid not in ids,
                         "must not match inside/near other tokens"))
    modal_texts = [r["text"] for r in reqs if r["kind"] == "modality"]
    for start in G.GOLD_BRD_MODALITY_STARTS:
        out.append(_inst("requirements", f"modality: '{start}...'",
                         any(t.startswith(start) for t in modal_texts)))
    for start in G.GOLD_BRD_MODALITY_FORBIDDEN:
        out.append(_inst("requirements", f"no false modality: '{start}...'",
                         not any(t.startswith(start) for t in modal_texts),
                         "'must-have' is not a modality requirement"))
    return out


def grade_mechanisms() -> list[dict]:
    out = []
    found_sdd = {m["mechanism"] for m in
                 find_mechanisms(build_doc_model(G.GOLD_SDD))}
    for mech in sorted(G.GOLD_SDD_MECHANISMS):
        out.append(_inst("mechanisms", f"finds '{mech}'", mech in found_sdd))
    found_plain = {m["mechanism"] for m in
                   find_mechanisms(build_doc_model(G.GOLD_PLAIN_ENGLISH))}
    for word in sorted(G.GOLD_PLAIN_FORBIDDEN):
        out.append(_inst("mechanisms", f"plain-English: no '{word}'",
                         word not in found_plain,
                         f"plain-doc finds: {sorted(found_plain)}"))
    return out


def grade_evidence() -> list[dict]:
    out = []
    crits = [c for c, _ in G.GOLD_EVIDENCE] + G.GOLD_EVIDENCE_ABSENT
    located = locate_candidates(G.GOLD_SDD, crits)["per_criterion"]
    doc = build_doc_model(G.GOLD_SDD)
    title_by_ref = {s["ref"]: s["title"] for s in doc["sections"]}
    for crit, fragment in G.GOLD_EVIDENCE:
        cands = located[crit["id"]]["candidates"]
        hit = any(fragment.lower() in title_by_ref.get(c["section"], "").lower()
                  for c in cands)
        out.append(_inst("evidence", f"{crit['id']} -> section '{fragment}'",
                         hit, f"got: {[c['section'] for c in cands]}"))
    for crit in G.GOLD_EVIDENCE_ABSENT:
        cands = located[crit["id"]]["candidates"]
        out.append(_inst("evidence", f"{crit['id']} absent -> no candidates",
                         not cands, f"got: {[c['section'] for c in cands]}"))
    return out


def grade_traceability() -> list[dict]:
    out = []
    reqs = extract_requirements(G.GOLD_BRD)["requirements"]
    rows = {r["id"]: r for r in
            traceability_matrix(reqs, G.GOLD_SDD)["rows"]}
    for rid, want in sorted(G.GOLD_TRACE.items()):
        got = rows.get(rid, {}).get("status", "missing")
        ok = (got == want if want != "addressed_or_referenced"
              else got in ("addressed", "referenced"))
        out.append(_inst("traceability", f"{rid} = {want}", ok, f"got: {got}"))
    return out


def grade_anchors() -> list[dict]:
    out = []
    crits = {c["id"]: c for c, _ in G.GOLD_EVIDENCE}
    for anchor, cid, grounded in G.GOLD_ANCHORS:
        rel = anchor_relevance(anchor, crits[cid])
        ok = (rel > 0.0) if grounded else (rel == 0.0)
        label = "grounded" if grounded else "ungrounded"
        out.append(_inst("anchors", f"{label}: '{anchor[:40]}...' vs {cid}",
                         ok, f"relevance={rel}"))
    return out


def grade_injection() -> list[dict]:
    out = []
    for text in G.GOLD_INJECTION_ATTACKS:
        flags = injection_lint(text)
        out.append(_inst("injection", f"flags: '{text[:45]}...'", bool(flags),
                         f"kinds: {[f['kind'] for f in flags]}"))
    for text in G.GOLD_INJECTION_BENIGN:
        flags = injection_lint(text)
        out.append(_inst("injection", f"clean: '{text[:45]}...'", not flags,
                         f"kinds: {[f['kind'] for f in flags]}"))
    return out


def grade_blinding() -> list[dict]:
    out = []
    for text, token in G.GOLD_BLINDING_ATTACKS:
        got = blinding_scan(text)
        out.append(_inst("blinding", f"finds '{token}'", token in got,
                         f"got: {got}"))
    for text in G.GOLD_BLINDING_BENIGN:
        got = blinding_scan(text)
        out.append(_inst("blinding", f"clean: '{text[:45]}...'", not got,
                         f"got: {got}"))
    return out


def grade_release() -> list[dict]:
    out = []
    enriched = enrich_queries(G.GOLD_RELEASE_QUERIES)
    for orig, enr in zip(G.GOLD_RELEASE_QUERIES, enriched):
        key = orig["mechanism_key"]
        preserved = all(enr.get(k) == v for k, v in orig.items())
        out.append(_inst("release", f"{key}: original fields preserved",
                         preserved))
        name = orig["mechanism_name"]
        out.append(_inst("release", f"{key}: salesforce-scoped variant",
                         f'"{name}" site:help.salesforce.com'
                         in (enr.get("nlp_variants") or [])))
    review = review_evidence(G.GOLD_RELEASE_EVIDENCE, G.GOLD_RELEASE_QUERIES)
    for (key, idx), (want_dom, want_grounded) in sorted(
            G.GOLD_RELEASE_LABELS.items()):
        row = review["per_mechanism"][key]["items"][idx]
        dom_ok = row["salesforce_domain"] == want_dom
        grd_ok = (row["relevance"] > 0.0) == want_grounded
        out.append(_inst("release", f"{key}[{idx}]: domain={want_dom}",
                         dom_ok, f"got: {row['salesforce_domain']}"))
        out.append(_inst("release", f"{key}[{idx}]: grounded={want_grounded}",
                         grd_ok, f"relevance={row['relevance']}"))
    return out


def grade_verdicts() -> list[dict]:
    """Autonomous screener vs hand-labeled ground truth on GOLD_SDD:
    judge A (evidence-primary) must match exactly; judge B (coverage-
    primary) may be at most one step stricter, never looser/two off."""
    import auto_judge
    out = []
    order = {"Present": 3, "Partial": 2, "Absent": 1}
    crits = {c["id"]: c for c, _ in G.GOLD_EVIDENCE}
    crits.update({c["id"]: c for c in G.GOLD_EVIDENCE_ABSENT})
    crits.update({c["id"]: c for c in G.GOLD_VERDICT_EXTRA_CRITERIA})
    sent_terms = auto_judge._sentence_terms(G.GOLD_SDD)
    located = locate_candidates(G.GOLD_SDD, list(crits.values()))["per_criterion"]
    for cid, want in sorted(G.GOLD_VERDICTS.items()):
        cands = located.get(cid, {}).get("candidates", [])
        va = auto_judge._auto_verdict(crits[cid], G.GOLD_SDD, "claude-code",
                                      sent_terms, cands)["verdict"]
        vb = auto_judge._auto_verdict(crits[cid], G.GOLD_SDD, "gemini",
                                      sent_terms, cands)["verdict"]
        out.append(_inst("verdicts", f"A {cid} = {want}", va == want,
                         f"got: {va}"))
        b_ok = order[want] - order.get(vb, 0) in (0, 1)
        out.append(_inst("verdicts", f"B {cid} within one strict step of {want}",
                         b_ok, f"got: {vb}"))
    return out


def grade_sections() -> list[dict]:
    """Unsupervised heading recognition vs hand-labeled canonical components."""
    from nlp.section_match import match_sections
    out = []
    got = {r["ref"].split()[0].lstrip("\u00a7"): r["component"]
           for r in match_sections(G.GOLD_SECTIONS_DOC)["sections"]}
    for num, want in sorted(G.GOLD_SECTION_LABELS.items()):
        label = want or "(unrecognized)"
        out.append(_inst("sections", f"heading {num} -> {label}",
                         got.get(num) == want, f"got: {got.get(num)}"))
    return out


def grade_doctype() -> list[dict]:
    from nlp.doc_classifier import classify
    out = []
    for name, want in G.GOLD_DOCTYPES:
        got = classify(getattr(G, name))["type"]
        out.append(_inst("doctype", f"{name} = {want}", got == want,
                         f"got: {got}"))
    return out


# ---------------------------------------------------------------- harness
GRADERS = [grade_requirements, grade_mechanisms, grade_evidence,
           grade_traceability, grade_anchors, grade_injection,
           grade_blinding, grade_release, grade_verdicts,
           grade_sections, grade_doctype]


def run_benchmark() -> dict:
    instances = []
    for g in GRADERS:
        instances.extend(g())
    components = {}
    for i in instances:
        c = components.setdefault(i["component"],
                                  {"total": 0, "passed": 0, "failures": []})
        c["total"] += 1
        if i["pass"]:
            c["passed"] += 1
        else:
            c["failures"].append(f"{i['check']} ({i['detail']})")
    for c in components.values():
        c["accuracy"] = round(c["passed"] / c["total"], 4)
    total = len(instances)
    passed = sum(1 for i in instances if i["pass"])
    return {"threshold": THRESHOLD,
            "components": components,
            "overall": {"total": total, "passed": passed,
                        "accuracy": round(passed / total, 4)},
            "ok": (passed / total >= THRESHOLD
                   and all(c["accuracy"] >= THRESHOLD
                           for c in components.values())),
            "instances": instances}


def main(argv: list[str]) -> int:
    res = run_benchmark()
    if "--json" in argv:
        slim = {k: v for k, v in res.items() if k != "instances"}
        print(json.dumps(slim, indent=1, sort_keys=True))
        return 0 if res["ok"] else 1
    print("NLP accuracy benchmark — gold corpus, threshold "
          f"{THRESHOLD:.0%} per component and overall\n")
    print(f"{'component':<14}{'passed':>8}{'total':>7}{'accuracy':>10}  verdict")
    print("-" * 52)
    for name in sorted(res["components"]):
        c = res["components"][name]
        verdict = "PASS" if c["accuracy"] >= THRESHOLD else "FAIL"
        print(f"{name:<14}{c['passed']:>8}{c['total']:>7}"
              f"{c['accuracy']:>9.1%}  {verdict}")
    o = res["overall"]
    print("-" * 52)
    print(f"{'OVERALL':<14}{o['passed']:>8}{o['total']:>7}"
          f"{o['accuracy']:>9.1%}  {'PASS' if res['ok'] else 'FAIL'}")
    fails = [f for c in res["components"].values() for f in c["failures"]]
    if fails:
        print("\nfailed instances:")
        for f in fails:
            print(f"  - {f}")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
