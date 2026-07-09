# Application Flow — W2 Evaluation Bench v2.0

Document 2 of 6 · Behavioral specification (consumes: PRD)
Authoritative for: run lifecycle, state machine, packet protocol, actor
sequences, failure paths. Backend Schema (doc 5) defines the data shapes these
flows read and write.

---

## 1. Actors

| Actor | Where it runs | Role |
|---|---|---|
| Operator | Browser | Uploads inputs; optionally approves a paused checkpoint; downloads deliverables |
| Console | Static SPA served by the app | Renders state; never computes |
| Server | Cloud Run (single instance) | Deterministic brain: orchestrator, engine v4.7, packet store, validation, reports. Zero model calls |
| Runner | Operator-controlled machine/VM (daemon) | Claims packets; routes to judges; posts results. Holds the only Claude credential |
| Judge A | Claude Code (`claude -p`) on the runner box | Subscription-billed model judgment |
| Judge B | Gemini API (HTTPS from runner) | Google-billed model judgment |

## 2. One-time setup flow (not per-run)

1. Deploy: `PROJECT=… W2APP_TOKEN=$(openssl rand -hex 24) bash scripts/deploy_cloudrun.sh`
   → Cloud Run service, GCS bucket mounted at `/data`, token-protected `/api`.
2. Each evaluating member, on their own laptop (one time; full steps in
   doc 07-installation-guide.md):
   `curl -fsSL https://<app-url>/install.sh | bash -s -- --token <their-token>`
   → installs Claude Code if missing → browser opens Anthropic's login for
   their Team seat (`claude setup-token`; credential stays local) → runner
   installed as a user-level service → billing-guard (G1–G3) + Gemini
   preflights → first heartbeat. Console shows "runner connected".
3. Org Gemini key (`GEMINI_API_KEY`, paid tier) distributed in the installer
   env or added to `~/.w2/env`.
Weekly-cadence behavior: a member's run executes only while THEIR runner is
online (owner affinity); a sleeping laptop pauses the run at
`awaiting_packets`, and it resumes on wake — surfaced in the console as
"waiting for your runner".

## 3. Run status machine (server-authoritative)

Statuses: `created → running ⇄ awaiting_packets → [awaiting_checkpoint] →
running → done | error | stopped`

| Status | Meaning | Exits via |
|---|---|---|
| created | state.json written, inputs saved | immediate `advance()` |
| running | orchestrator executing deterministic batches | next wait-point or done |
| awaiting_packets | ≥1 open packet; runner work pending | last packet result posted → `advance()` |
| awaiting_checkpoint | pausing D.5 chosen at upload; panel built | POST approve → running; POST reject → stopped |
| stopped | operator stop at paused D.5 | terminal |
| error | any batch/validation/tripwire failure; message + traceback in state | terminal (new run to retry) |
| done | report built; deliverables downloadable | terminal |

`advance(run_id)` is idempotent: every batch checks its own output artifact
before executing; it is invoked on run creation, on every packet-result POST,
and on checkpoint approval.

## 4. Stage rail (Mode A)

`S0 intake → S1 setup → S2 mapping+crosswalk → S3 dual-judge scoring →
S3.5 consensus → D5 checkpoint (auto) → S4 sheets+lift → S5 reveal+report`

### S0–S1 (deterministic, no packets)
- intake_validate: hashes inputs, seals `.lane-mapping` escrow
  (label↔identity), emits lane_files (label→path), applicability flags,
  integration_count, run-record.
- zms_load: filters the frozen 99-criterion calibration by engagement flags →
  content + dims-1-3 + dims-4-7 slices + summary.

### S2 (packets: components ×2 lanes, features ×2 lanes → deterministic)
- Runner executes 4 packets (Judge A only — extraction, not scoring).
- content_mapping_classify per lane → completeness verdicts, Dim-4 floor cap
  (missing/stub components: 0 → no cap; 1–2 → cap 10; ≥3 → cap 7), workbook.
- release_crosswalk extract → queries; evidence packet only if live evidence
  chosen (web-enabled, Judge A); resolve → release-awareness findings with RR
  deductions (−3 confirmed not-in-force; −1 in-force-unverified on live path;
  cumulative cap −9; register path never penalises unverified).

### S3 dual-judge scoring (packets: pass ×8 = 2 lanes × 2 groups × 2 judges)
- Server creates per (lane, group) two byte-identical `pass` packets;
  `meta.judge` differs. Runner routes by `meta.judge`: claude-code → `claude -p`
  under guards; gemini → Gemini API.
- Each result = full scorecard: `dim_scores`, nested `sub_scores`,
  per-criterion `verdicts` {verdict, verbatim evidence_anchor, sdd_ref,
  components_present/partial/absent}.

### S3.5 consensus (deterministic diff → reconcile packets ≤4 → deterministic merge)
1. Server diffs Judge A vs Judge B per (lane, group):
   - criterion divergence: verdict mismatch, or Present/Partial anchors judged
     non-equivalent;
   - sub-score divergence: |Δ| > 20% of sub max;
   - dimension divergence: |Δ| > 10% of dim max.
2. Zero divergences → consensus = agreed scorecard; skip to bundle.
3. Else one `reconcile` packet per (lane, group) carrying only divergent
   items: both judges' entries + the SDD. Executor: Judge A (blinded; R14
   scan applies to its output). Per item it must return a ruling ∈
   {adopt_claude, adopt_gemini, meet_between(with cause), dissent} with a
   verbatim SDD citation justifying it.
4. Server merges deterministically: agreed → pass-through; ruled → ruling
   applied; dissent → conservative value (weaker verdict; min score) and a
   dissent record preserved. Consensus sub/dim scores recomputed bottom-up;
   Dim-3 net of RR cap; Dim-4 floor applied to consensus.
5. Agreement statistics computed (Backend Schema §6.5).

### Narrative + bundle + D5
- narrative packet ×2 lanes (Judge A): key_reasoning / narrative / citations
  from the CONSENSUS coding digest (per-dimension capped digest).
- Bundle assembly (v4.7 schema) + validation R1–R28. Any failure → error with
  the rule text verbatim.
- Checkpoint panel built (blinded): per-lane totals, per-dim means,
  agreement rate, dissent count, floor, release summary. Auto-approve default
  (recorded); pause if chosen.

### S4–S5
- source_index_build per lane → score_sheet_populate (validates + fills
  Judge A / Judge B / Consensus columns) → lift_calculate on consensus totals
  (integration-heavy weight swap from run-record: Dim-5 10→15, Dim-7 15→10)
  with per-judge lifts as the uncertainty band.
- exec_narrative packet (blinded digest, Judge A).
- lane_reveal_apply: first and only escrow read → diagnostic-bundle
  (za_label, methodology_lift, agreement stats forwarded).
- report_build_substantive → diagnostic-report.docx (provenance badges,
  agreement stats, Dissent & Reconciliation annex, Appendix B release audit).
- status done; console shows lift + links.

## 5. Mode B flow

S0 → S1 → S2 (components, features, crosswalk on the single lane) →
S3 review ×2 groups ×2 judges (4 packets) → S3.5 consensus on findings
(match by zms_lens; divergent verdicts → 1 reconcile packet; dissents flag the
finding) → merge; build_ready = not_build_ready if any blocking finding else
build_ready_with_conditions if any `requires` else build_ready →
sdd_review_validate → sdd-review-report.docx. No checkpoint, no reveal.

## 6. Packet protocol (all flows)

Lifecycle: `create (server, idempotent by packet_id) → claim (runner GET
/api/packets/next?runner_id=…; the presenting token's member must equal the
run's owner; stale claims >90s are taken over by the same owner's runners) →
execute → POST result {result, usage} → server stores, fires advance()`.
Every /api/packets/next call doubles as a heartbeat for the presenting member.

Packet kinds and executors:

| kind | executor | count Mode A | count Mode B |
|---|---|---|---|
| components | Judge A | 2 | 1 |
| features | Judge A | 2 | 1 |
| evidence (live only) | Judge A (web) | 0–2 | 0–1 |
| pass | per meta.judge | 8 | 0 |
| reconcile | Judge A | 0–4 | 0–1 |
| review | per meta.judge | 0 | 4 |
| narrative | Judge A | 2 | 0 |
| exec_narrative | Judge A | 1 | 0 |

Packet ids: `components:Output A`, `pass:Output A:1-3:claude-code`,
`pass:Output A:1-3:gemini`, `reconcile:Output A:1-3`, `review:1-3:gemini`,
`exec_narrative` (URL-encoded on the wire; filenames sanitized).

## 7. Operator touchpoint inventory (per hands-free run)

1. **Upload** (files + options) — the single touchpoint.
   Then: zero. The checkpoint auto-approves (recorded); reconciliation is
   judge-ruled; the report link appears. Downloading is optional and
   decision-free. With the pausing checkpoint opt-in: exactly 2 touches.

## 8. Failure and edge flows

| Event | Behavior |
|---|---|
| Owner's runner offline (laptop asleep) | Packets stay open; run waits in awaiting_packets; console banner "waiting for YOUR runner — last seen <t>"; resumes on wake; stale claims taken over after 90s by the owner's runners only |
| Claude call fails | Runner logs, retries next poll; packet remains open |
| Gemini call fails / key missing | Panel preflight refuses at startup; mid-run failure leaves gemini packets open; operator env fix required (no silent single-judge fallback — provenance would lie) |
| Billing tripwire (G4 or server 402) | Runner halts; run → error with BILLING_TRIPWIRE message; no result stored |
| Bundle validation failure (R1–R28) | Run → error; failing rule text verbatim in state.error |
| Blinding leak in reconcile/narrative output | R14 fails validation → error (leak never reaches report) |
| Duplicate result POST | Second write ignored (result file exists) |
| Server restart (Cloud Run) | State on GCS volume; advance() resumes from artifacts on next trigger |
| Same-judge total disagreement (dissent-heavy run) | Run completes; agreement stats low; annex long; conservative consensus stands — this is signal, not failure |

## 9. Sequence (hands-free Mode A, condensed)

```
Operator → Server: POST /api/runs (brd, sdd_1, sdd_2, zenagent_is)
Server: S0–S1; create 4 mapping packets; status awaiting_packets
Runner ⇄ Server: claim/execute/post ×4 (Judge A)
Server: S2 deterministic; create 8 pass packets
Runner: 4× claude -p (guarded) + 4× Gemini API; post 8 scorecards
Server: diff; create ≤4 reconcile packets (else skip)
Runner: Judge A rules divergences; post
Server: merge consensus; create 2 narrative packets → Runner (Judge A)
Server: assemble bundles; validate R1–R28; build D5 panel; AUTO-APPROVE;
        sheets; lift; create exec_narrative packet → Runner (Judge A)
Server: reveal (escrow read #1); build report; status done
Operator (optional): GET download links
```
