# Changelog — W2 Evaluation Bench

## v2.0.1 (2026-07-06) — QA hardening + deployment kit

Post-release QA & security audit (`docs/qa-report.md`). Fixes:
- **Dockerfile**: image now includes `runner/` + `examples/` — the payload
  behind `/runner.zip` and `/install.sh`. Without this, Cloud Run deployments
  served an empty runner (production-blocking; local trees masked it).
- **Prompt-injection guard**: explicit instruction-hierarchy line (`DOC_GUARD`)
  in every v2.0 document-bearing packet prompt; dual scoring prompts remain
  byte-identical; frozen five-pass prompt untouched.
- **Server hardening**: 25 MiB upload ceiling (413; `W2_MAX_UPLOAD_MB`),
  constant-time member-token comparison, `X-Content-Type-Options` /
  `X-Frame-Options` / `Referrer-Policy` headers, `GET /healthz` probe.
- **Deployment kit**: `scripts/remote_smoke.sh` (16 read-only live-service
  checks; auto-run by `deploy_cloudrun.sh`), `.gcloudignore` (client documents
  never ride a source upload), `deploy/cloudbuild.yaml` (GitHub → Cloud Run
  pipeline: unit gate → build → SHA-tagged push → image-only deploy →
  remote smoke), docs 08 (OAuth-first deployment plan) and 09 (GitHub deploy
  user guide).

## v2.0 (2026-07-06) — dual-judge consensus (engine v4.6 → v4.7)

Built to the seven-document v2.0 spec set (`docs/00`–`07`; conflicts and
resolutions recorded in `docs/errata.md`). The v1.1 baseline is preserved at
tag/commit `v1.1-baseline`; its five-pass protocol is retired from the
product and frozen behind `EVAL_PROTOCOL=five-pass` (PRD D6, TRD §4).

### Protocol
- Five-pass single-judge scoring → **one pass per judge per lane×dim-group,
  two judges** (Claude via Claude Code subscription; Gemini via API), from
  byte-identical blinded packets (PRD D1/D2; FR-3).
- New deterministic consensus engine (`server/consensus.py`): strict 20%/10%
  divergence thresholds, anchor-equivalence tokenization, evidence-ruled
  reconciliation by a blinded Claude packet, conservative dissent resolution
  (weaker verdict / min score; NA never wins), Dim-3 netting + Dim-4 floor
  applied once post-merge to all three columns (FR-4; TR-12..14).
- Engine v4.7: `contracts.py` gains JUDGES, SUB/DIM_DELTA_FRAC, VERDICT_ORDER,
  JUDGE_INDEPENDENCE_ATTESTATION, PROTOCOLS; `judge_accumulate.py`;
  validator path R1 + R3–R28 (R2 retired; R26/R27/R28 new; R14/R25 extended
  over reconcile output and both judges' retained anchors); v4.7 score-sheet
  template (Judge A / Judge B / Consensus / Provenance columns, Judge_Record
  sheet, R1–R28 cover checklist); dual-judge lift from the scoring bundles
  (consensus headline, per-judge lifts, [min,max] band; bootstrap/ICC
  bypassed, TR-19).

### Reports (comprehensive + traceable; nothing from v4.6 reduced)
- Diagnostic Report: judge provenance badges, per-dimension cross-model
  agreement table with reliability labels, per-judge lift row + inter-judge
  band, DISSENT flags in the value table, new "Refinement areas by lane"
  section, new "Appendix D — Dissent & Reconciliation annex" (every
  divergence: both judges' verdicts + verbatim anchors, ruling + verbatim SDD
  citation, why-unresolved + conservative resolution).
- SDD Review Report: cross-model agreement block, CONTESTED cards on
  dissent-derived recommendations, dissent annex, findings-by-dimension prose
  now populated from the structured findings (v1.1 left it empty), correct
  build-readiness verdict on the cover (v1.1 always showed the default).

### Operations
- One-touch runs: D.5 auto-approve is the default (panel still built and
  recorded); pausing checkpoint is per-run opt-in (D5, FR-8).
- Multi-member: `W2APP_TOKENS` per-member auth, owner stamping, owner-pays
  claim affinity, heartbeat ledger + `GET /api/runners` (FR-13, TR-29).
- Self-service installer: `GET /install.sh` (personalized, idempotent) +
  `GET /runner.zip`, launchd + `systemd --user` service templates,
  `w2_runner.py --selfcheck` (FR-12, TR-30/31).
- Runner: panel is the default engine; routing by packet `meta.judge`; no
  silent judge fallback; Gemini free-tier fail-closed probe (D7/D8, TR-8/10).
- Server hardening: per-kind result shape validation (400, packet stays
  open), write-once results, judge-provenance check on posted results,
  billing tripwire unchanged (402 + loud halt).
- Console rebuilt (`/bench`): stage rail with consensus stage, concurrence
  meter (SVG dual tracks + dissent dots) with view-as-table fallback,
  per-judge usage line pinned at $0.00, read-only auto-approved checkpoint
  panel, revealed result with judge lifts + band + annex pointer. New
  Zennify-branded landing page at `/`.
- `scripts/smoke_e2e.sh` v2 = the release gate (T-6..T-12 inline: hands-free
  zero-touch, paused checkpoint, contested Mode B, tripwire/write-once/shape,
  auth+affinity, escrow, SDK greps, frozen five-pass leg).

### Billing invariants (unchanged, re-verified)
G1–G5 + server 402 tripwire carried forward verbatim; zero Anthropic API
spend; escrow never served, first read at reveal; Gemini paid-tier required.

## v1.1 — five-pass baseline
Working five-pass application (Cloud Run assets, guards, panel-mode runner,
mock smoke). Imported verbatim as the v2.0 baseline (`v1.1-baseline`).
