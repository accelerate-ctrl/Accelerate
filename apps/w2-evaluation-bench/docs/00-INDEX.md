# W2 Evaluation Bench v2.0 — Build Document Set

Seven documents specifying the dual-judge consensus build, written against the
working v1.1 codebase (`w2-evaluation-bench-v1.1.zip`) as baseline. Produced
2026-07-03; every constant cited was extracted from the running v1.1 engine.

Read order for a human: 01 → 02 → 03 → 04 → 05 → 06; give 07 to each evaluating member.
Feed order for Claude Code: give it 06 (implementation plan) as the driver and
the rest as references; start at Phase 0.

| # | File | Role |
|---|---|---|
| 1 | 01-PRD.md | What and why; functional requirements; **§7 locked decision log D1–D12** (binding on everything) |
| 2 | 02-application-flow.md | Behavior: lifecycle, state machine, stages, packet protocol, failure paths, one-touch inventory |
| 3 | 03-backend-schema.md | Data: storage layout, state/packet/scorecard/consensus/bundle schemas, R1–R28, HTTP API |
| 4 | 04-TRD.md | Technical requirements TR-1..28, architecture, testing T-1..11, migration constraints, risks |
| 5 | 05-ui-ux-brief.md | Console design: identity, screens, concurrence meter, states, writing rules, accessibility; §8 Zennify-branded landing page |
| 6 | 06-implementation-plan.md | Phases 0–6 with tasks, acceptance criteria, sequencing, risk register |
| 7 | 07-installation-guide.md | Per-member runner setup (one command or manual), weekly-cadence usage, troubleshooting |

Post-build documents (added after the build shipped):

| # | File | Role |
|---|---|---|
| 8 | 08-cloud-run-deployment-guide.md | Complete Cloud Run deployment plan: OAuth client → every component → verified live service → member onboarding → operations |
| 9 | 09-github-deploy-user-guide.md | Operator guide: first deploy from GitHub via Cloud Shell, then push-to-deploy via the Cloud Build trigger (`deploy/cloudbuild.yaml`) |
| — | qa-report.md | v2.0 QA & security audit: completeness matrix, E2E functionality evidence, security + prompt-injection review, hardening fixes |
| — | errata.md | Every doc-vs-code conflict found during the build, with its ruling |

Precedence on conflict (also stated in the plan): Backend Schema wins on data
shapes, Application Flow on behavior, PRD on scope; record any found conflict
as an erratum.

Non-negotiables carried through all six: zero Anthropic API spend (guards
G1–G5 + server tripwire); blinding escrow never served and first read at
reveal; one operator touchpoint per hands-free run; nothing silently averaged
— every consensus value is agreed, evidence-ruled, or a conservative
resolution of a recorded dissent.
