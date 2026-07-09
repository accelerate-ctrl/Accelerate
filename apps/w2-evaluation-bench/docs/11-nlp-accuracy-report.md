# NLP accuracy report — pre-intelligence layer v1.1

**Verdict: every component measures 100% on the gold corpus (87/87 labeled
instances), above the required 95% bar. The bar is enforced in CI — any
change that drops a component below 95% fails the test suite.**

Measured 2026-07-09 at engine v4.7 + pre-intelligence v1.1.

## 1. What was measured, and how

The pre-intelligence layer (`engine/evaluate-sdd/scripts/nlp/`) is the
deterministic ML/NLP stage that prepares and verifies — never judges —
before and after the intelligent layer (Claude + Gemini) runs. Its outputs
are advisory packet content and flags routed into evidence-ruled
reconciliation, so its accuracy directly shapes what the judges see.

Accuracy is measured against a **hand-labeled gold corpus**
(`tests/gold_corpus.py`): a synthetic BRD/SDD pair plus attack/benign text
sets in which every label is an objective fact about the text (an ID either
appears or it doesn't; a mechanism either is named or it isn't). Each label
is one graded instance; a component's accuracy is the share of instances it
gets right.

The corpus is deliberately **adversarial** — it concentrates instances where
a naive implementation fails:

- plain-English uses of Salesforce words that must NOT be flagged as
  mechanisms ("children play in the **sandbox**", "our office **dashboard**",
  "the team **profiles** customer segments");
- plural mechanism mentions that must still be found ("record **types**",
  "sharing **rules**", "permission set **groups**", "platform **events**");
- ID lookalikes that must NOT match the requirement pattern (`TRANSF-19`
  must not yield `SF-19`);
- compound adjectives that must NOT read as modality requirements
  ("a **must-have** list");
- ten paraphrased prompt-injection attacks vs ten benign lookalikes
  ("ignore your previous instructions…" vs "the system shall **ignore**
  duplicate webhook deliveries");
- grounded vs ungrounded evidence anchors, on-domain vs off-domain release
  evidence, and R14 blinding-token lookalikes.

One measurement path serves both surfaces:

| Surface | Command | Role |
|---|---|---|
| CLI benchmark | `python3 scripts/nlp_benchmark.py` | table + per-instance failures, exit 1 below bar |
| CI gate | `tests/test_nlp_accuracy.py` (in the standard suite) | fails the build if any component or the overall score drops below 95% |

The benchmark is deterministic (asserted by
`test_benchmark_deterministic`), and the gate also asserts the corpus keeps
its negative instances — the 95% floor cannot be quietly satisfied by
deleting the hard cases.

## 2. Results (v1.1, current)

| Component | What it feeds | Instances | Accuracy |
|---|---|---|---|
| requirements | BRD requirement registry → Dims 1/2/6 backbone | 11 | **100%** |
| mechanisms | Salesforce mechanism inventory → packets + crosswalk floor | 22 | **100%** |
| evidence | per-criterion candidate location → advisory retrieval hints | 7 | **100%** |
| traceability | BRD→SDD coverage pre-map → gap candidates | 4 | **100%** |
| anchors | post-judgment anchor verification → weak-evidence flags | 8 | **100%** |
| injection | instruction-shaped-text lint → DOC_GUARD complement | 20 | **100%** |
| blinding | R14 token family scan at intake | 5 | **100%** |
| release | crosswalk query enrichment + R23 domain/relevance review | 10 | **100%** |
| **Overall** | | **87** | **100%** |

## 3. What the benchmark caught (v1.0 baseline → v1.1 fixes)

The first run against the gold corpus measured **89.7% overall** and
exposed three real defect classes; each was fixed and re-measured:

| Defect (v1.0 baseline) | Measured impact | Fix (v1.1) |
|---|---|---|
| Plural mechanism mentions missed — "Record types", "sharing rules", "permission set groups", "platform events", "report types", "unlocked packages" did not match their singular lexicon phrases | mechanisms recall 11/17; component 63.6% | plural-tolerant phrase matching (`(?:e?s)?` on the final word) with canonical folding so "Record types" reports as `record type` |
| Plain-English false positives — "office dashboard", "children play in the sandbox" reported as Salesforce mechanisms | 2 false mechanisms per plain document | ambiguous single words (`profile`, `dashboard`, `sandbox`, `middleware`, `callout`) now count only when the surrounding ±120-char window carries an unambiguous mechanism or a platform cue — still fully deterministic |
| "A must-have list…" captured as a modality requirement | 1 false requirement per affected BRD | modality regex now rejects compound adjectives: `\b(shall|must|should)\b(?!-)` |

Re-run after fixes: **100.0% overall, all components PASS** (§2). The full
unit suite (83 tests) and the end-to-end smoke (both protocol modes, billing
tripwire, auth matrix, escrow isolation, pre-intel packet check) pass at the
same commit.

## 4. Components already at 100% at baseline

Injection lint flagged all 10 paraphrased attacks with zero false positives
on the 10 benign lookalikes; anchor relevance separated all 8 grounded/
ungrounded anchors; evidence location hit the correct section for all 6
present criteria and produced no candidates for the absent one; traceability
labeled all 4 gold requirements correctly (including SF-3.1, addressed by
substance without an ID citation); release review labeled every
domain/grounding case correctly and preserved every original query field.

## 5. Scope and honesty notes

- **What 100% means:** the layer is measured against a labeled corpus built
  to concentrate its likeliest failure modes, not against all possible
  documents. The corpus is versioned with the code; extending it with any
  newly observed failure shape is the intended maintenance path — add the
  case, watch the gate fail, fix, re-measure.
- **Why the bar is per-component:** an aggregate can hide a weak component
  behind strong ones. Every component must independently clear 95%.
- **The covenant is unchanged:** these components prepare and verify only.
  Even a wrong advisory hint cannot decide a verdict — hints are marked
  advisory in the packet, and every weak-evidence flag routes into the
  evidence-ruled reconciliation where the intelligent layer rules with a
  citation.
- **Determinism:** same inputs ⇒ byte-identical outputs (no model calls, no
  randomness, pure stdlib), so these numbers reproduce exactly on any
  machine: `python3 scripts/nlp_benchmark.py`.
