# UI/UX Design Brief — W2 Evaluation Bench v2.0

Document 5 of 6 · Design brief (consumes: PRD, Application Flow)
Surface: the operator console — a single-page app served by the FastAPI
server. One user (the evaluation operator), one job: submit an evaluation and
trust what comes back.

---

## 1. Design thesis

This is a **bench instrument, not a dashboard**. The operator touches it once
per run; the interface's job is to make the invisible trustworthy — to show
that a blinded, two-model, evidence-gated process is running correctly without
asking anything of the user. Every design choice should serve *legibility of
process*: what stage, which judge, how much agreement, where the dissent.

The v2.0 signature element is the **concurrence meter**: dual judge tracks
rendered as two thin parallel lines per dimension that fuse into one solid
consensus line where the judges agree and visibly split where they dissent.
It is the product's argument drawn as a picture, and it appears in the run
detail, the checkpoint panel, and (statically) in the report.

## 2. Identity

Palette — inherited from the deliverable's own styler (report_style.py), so
console and report read as one instrument:

| Token | Hex | Use |
|---|---|---|
| deep | #1c4a4d | header, headings, primary text accents |
| teal | #139f94 | primary actions, Judge A (Claude) track |
| sub | #22bcad | progress, completed stages |
| blue | #8094c0 | Judge B (Gemini) track, blinded-label styling |
| pos | #059669 | done states, positive lift |
| neg | #c25008 | warnings, stops, negative lift, dissent markers |
| paper/card | #f2f5f4 / #ffffff | background / surfaces |

Type: IBM Plex Mono (or system mono fallback) for identifiers, data, tokens,
usage numbers — the instrument voice; Avenir Next / Segoe UI stack for labels
and prose. No decorative display face: restraint is the aesthetic; the
concurrence meter is the one expressive element.

Motion: stage-rail fills and meter fusion animate on state change only
(200ms ease); respect `prefers-reduced-motion`. No ambient animation.

## 3. Screens & components

### 3.1 Console layout (unchanged shell)
Routes: `/` serves the landing page (§8); `/bench` serves this console. Both
are static and exempt from token auth; the console prompts for the token on
its first API call.
Two columns: left — New run card, Runs list, Runner card; right — Run detail.
Header: product name, framework version tag, and the standing guard line:
`runner: subscription-only · API keys refused · billing tripwire armed`.

### 3.2 New run card
- Three file inputs (BRD; SDD 1; SDD 2 "leave empty for Mode B review").
- Mode A options (revealed when SDD 2 present): ZenAgent lane (SDD 1 / SDD 2);
  Release evidence (Register offline default / Live via runner).
- Run options row: **Checkpoint** select — `Hands-free (default)` /
  `Pause at D.5 for me`; Judging is displayed as a fixed badge
  `Panel: Claude + Gemini` (not a choice in v2.0 — communicate, don't ask).
- Primary button: `Start evaluation`. Microcopy under the card:
  "Three files → blinded comparison with methodology lift. Two files → design
  review. You won't be needed again until the report."
- The one-touch promise is explicit UI copy; it is the product's headline
  behavior.

### 3.3 Runs list
Row: run id (mono) · mode chip · status badge (colors: awaiting_packets teal,
awaiting_checkpoint neg, done pos, error/stopped dark rust, else blue).
Hands-free runs never show awaiting_checkpoint.

### 3.4 Run detail
- Status header + **stage rail** (v2.0 stages):
  `intake → setup → mapping → dual scoring → consensus → checkpoint →
  sheets+lift → reveal+report`. Completed = sub teal; current = neg accent;
  future = line gray. The rail is the persistent "where am I" spine.
- **Judging panel** (v2.0 NEW, appears from dual-scoring onward):
  - Concurrence meter: per dimension 1–7, Judge A line (teal) and Judge B
    line (blue) at their score positions over the dim scale; fused solid bar
    when within threshold; a split with a neg dot marks a dissent. Hover /
    tap → criterion-level tooltip (verdicts + provenance).
  - Stat chips: `verdict agreement 91%` · `score concordance 0.88` ·
    `dissents 2` · reliability label text.
- **Open packets table** (while awaiting): packet id, kind, lane (blinded
  label styled in blue mono), judge badge (CC teal / GM blue), claimed-by.
- **Usage line**: `subscription usage · N packets · X in / Y out (Claude) ·
  X in / Y out (Gemini) · reported API cost $0.00 (must stay 0.00)`.
- **Checkpoint panel** (only when paused by opt-in): blinded table — totals,
  per-dim means, agreement rate, dissent count, mapping floor, release
  summary per lane; buttons `Proceed to score sheets` / `Stop with reason`
  (neg). For hands-free runs the same panel renders read-only with the badge
  `auto-approved · recorded at <time>` — the audit trail is visible even when
  no one was asked.
- **Deliverables**: link chips per artifact (report first). Token appended to
  href when auth is active.
- **Revealed result** (Mode A done): large mono lift figure colored pos/neg;
  line: `<label> resolved to ZenAgent · judge lifts: Claude +X / Gemini +Y ·
  concurrence <overall>`; sub-line links the annex: "2 dissents — see
  Dissent & Reconciliation annex in the report".

### 3.5 Token prompt
First 401 → minimal modal prompt for the server token (stored in
localStorage). No account UI; this is deliberate.

## 4. States, errors, empty

- Empty runs list: "No runs yet. Upload a BRD and one or two SDDs to start."
- Runner offline (open packets unclaimed > 2 min): banner in run detail —
  "Waiting for your runner. Check the daemon on your machine:
  `systemctl status w2-runner`." Neutral tone; the system is waiting, not
  broken.
- error status: neg panel with the verbatim failing message (rule text
  included when validation failed) and "Start a new run to retry — artifacts
  from this run remain downloadable where present."
- BILLING_TRIPWIRE error: distinct copy — "Halted deliberately: a packet
  reported a billable API cost. No result was stored. Fix the runner's
  credentials (subscription only) and start a new run." This error should
  feel like the system protecting the user, because it is.
- stopped: gray panel with the operator's recorded reason.

## 5. Writing rules

- Blinded labels only ("Output A/B") anywhere pre-reveal; the words
  ZenAgent/OTS never render before the revealed-result block.
- Buttons say what happens: `Start evaluation`, `Proceed to score sheets`,
  `Stop with reason`. Toast/badge tense matches: `Auto-approved`, `Done`.
- Numbers in mono; sentences in sans. No exclamation marks; no apology copy.
- Judge names in UI: "Claude" and "Gemini"; the canonical engine ids
  (`claude-code`, `gemini`) appear only in tooltips, packet tables, and logs.
- The interface never says "AI is thinking" — it names the actual work:
  "Judge B scoring dimensions 4–7".

## 6. Accessibility & quality floor

Keyboard: full tab order, visible focus (2px deep outline); the concurrence
meter has a table-equivalent rendering toggled by "view as table" (also the
narrow-viewport default). Color is never the only channel: judge tracks carry
CC/GM glyph labels; dissent dots pair with a count badge. Contrast ≥ 4.5:1 on
paper. Responsive to 380px: columns stack, tables scroll, the rail compresses
to dots+current-label. Polling at 4s with backoff when tab hidden.

## 7. Out of scope

Theming, dark mode, multi-user presence, run editing, in-console report
preview (the .docx is the artifact of record).

## 8. Landing page (v2.0 addition)

### 8.1 Purpose and audience
The first-touch surface at `/`: for Zennify stakeholders and report
recipients who will never operate the bench but must trust what it produces.
Its job is a plain-language account of **what happens behind the scenes**
between upload and report, and one call to action into the console. It is an
explanation, not a sales page.

### 8.2 Identity — official Zennify brand (distinct from the console)
The landing wears the corporate brand; the console keeps its instrument
identity (§2). Both are teal families, so the transition reads as one product.

| Token | Hex | Use |
|---|---|---|
| DARK_TEAL | #1E4A48 | hero background, footer |
| TEAL | #27BBAF | headings, primary CTA |
| MINT | #79E2BF | highlights on dark, pipeline accents |
| LIGHT_MINT / ICE | #B0EDD3 / #E8F7F6 | soft highlights / card backgrounds |
| DEEP_TEAL / DARK_BG | #185F60 / #1E3A3A | mid-dark variety / alt dark bands |
| TEXT_DARK / TEXT_MUTED | #1C4A4D / #6B8A8D | body / captions |
| Accents (sparingly) | A5C6FF · B19CD8 · FFCB99 · 139F94 | pipeline step glyphs only |

Type: **DM Sans** exclusively — SemiBold for headlines, Medium for
subheads, Regular for body. Numbers may use the console mono only inside the
pipeline diagram. Motion: one orchestrated hero reveal on load (staggered
150ms) and a single scroll-triggered draw of the pipeline band; nothing else;
respect `prefers-reduced-motion`.

### 8.3 Sections, top to bottom
1. **Hero** (DARK_TEAL, white + MINT text): Zennify wordmark; product name;
   headline: "Two models. One blinded verdict."; subhead: "The W2 Evaluation
   Bench scores solution designs against Zennify's frozen senior-SA
   calibration — judged independently by Claude and Gemini, reconciled on
   evidence, and delivered as an audit-ready report."; primary CTA
   `Open the bench` → /bench; quiet secondary line: "Runs on your
   subscription. Zero API billing."
2. **Behind the scenes** (ICE background): a seven-step horizontal pipeline
   band — the console's stage rail redrawn as a marketing graphic — each step
   a card with glyph, name, and 1–2 sentences:
   ① Upload — a BRD and one or two SDDs; the only human step.
   ② Sealed blinding — lane identities locked in an escrow no one and
   nothing reads until the final step; judges see only "Output A/B".
   ③ Frozen calibration — 99 criteria from Zennify's SDD standard and the
   Salesforce Well-Architected framework, filtered to the engagement.
   ④ Dual-judge scoring — Claude and Gemini each score every criterion
   independently from byte-identical packets, quoting the document verbatim
   for every verdict.
   ⑤ Evidence-ruled consensus — divergences are reconciled only by pointing
   at what the SDD actually says; genuine disagreements are preserved as
   dissents and resolved conservatively, never averaged away.
   ⑥ 28-rule validation — every anchor, citation, attestation, and deduction
   must pass the framework's validation gate before a report can exist.
   ⑦ Sealed reveal & report — the escrow is opened last; the methodology
   lift is oriented and the branded report is built with a full audit trail.
3. **Guarantees strip** (four ICE cards on white): Blinded until the last
   step · Two independent model families — dissents preserved · Every claim
   anchored verbatim to your documents · Zero API billing — subscription
   tokens only, with tripwires.
4. **The judges** (DARK_BG band): two cards — Claude (via Claude Code, on
   Zennify's subscription) and Gemini (via Google's API) — one line each on
   independence: neither sees the other's output before reconciliation.
5. **Footer** (DARK_TEAL): internal-tool notice, framework version (v4.7),
   link to the document set, `Open the bench`.

### 8.4 Writing rules (landing-specific)
Plain mechanism language; no hype, no exclamation marks, no "AI magic".
ZennAgent MAY be named on the landing page (product-level description) — the
blinding rule in §5 governs run data inside the console, not the product
story. Numbers used must be true ones from this document set (99 criteria,
28 rules, two judges, one human step).

### 8.5 Quality floor
Same as §6: contrast ≥ 4.5:1 (check MINT-on-DARK_TEAL sizes), full keyboard
order, pipeline band collapses to a vertical list under 700px, hero CTA
reachable without scroll on 380px.
