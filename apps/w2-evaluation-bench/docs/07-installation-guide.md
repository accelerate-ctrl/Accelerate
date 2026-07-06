# Installation Guide — W2 Evaluation Bench Runner (per member)

Document 7 of 7 · For each evaluating member · One-time setup, ~10 minutes
You need this once. Afterwards, using the bench is: open the app, upload your
deal's documents, come back for the report.

---

## What you are installing, in one paragraph

The web app (the bench) lives in the cloud, but the AI judging runs on **your
laptop**, under **your own Claude Team seat** — that's how the organization
uses zero Claude API credits. You'll install a small background service (the
"runner") that wakes up when you start an evaluation, does the judging via
Claude Code on your seat plus Gemini on the org's Google key, and goes back to
sleep. Your login happens once, in your own browser, on Anthropic's own page;
your credential never leaves your machine.

## Before you start (checklist)

- [ ] A **premium seat** on the organization's Claude Team plan (you can use
      Claude Code — if `claude` works for you anywhere, you're set).
- [ ] Your **personal bench token** and the **app URL** — from the bench
      administrator.
- [ ] The org **Gemini API key** (administrator provides; it's shared).
- [ ] macOS or Linux laptop, or Windows with WSL2. Python 3.10+.
      (The installer adds Node/Claude Code if missing.)

## Option A — one-command install (recommended)

Open a terminal and run (paste your real URL and token):

```bash
curl -fsSL https://YOUR-BENCH-URL/install.sh?token=YOUR-TOKEN | bash
```

What it does, step by step, visibly:
1. Installs the Claude Code CLI if you don't have it.
2. Runs `claude setup-token` → **your browser opens Anthropic's login. Sign
   in with your Team account.** A long-lived credential is minted and stored
   locally (nowhere else).
3. Installs the runner to `~/.w2/` and registers it as a background service
   (launchd on macOS, systemd --user on Linux/WSL) that starts on login.
4. Writes `~/.w2/env` (your bench token, the server URL, the Gemini key —
   file permissions locked to you).
5. Runs a self-check and prints the verdict you want to see:

```
[selfcheck] billing guard ......... PASS  (no API keys in scope; subscription auth OK)
[selfcheck] gemini co-judge ....... PASS  (paid tier)
[selfcheck] bench reachable ....... PASS  (hello, alice)
[selfcheck] runner service ........ RUNNING
```

Then open the bench in your browser — the header of the console should show
**"your runner: connected"**. Done.

## Option B — manual install

1. **Claude Code**: `npm install -g @anthropic-ai/claude-code`, then
   `claude setup-token`, sign in with your Team seat, and put the printed
   token in your environment as `CLAUDE_CODE_OAUTH_TOKEN` (or simply run
   `claude login` interactively instead).
2. **Runner files**: download `runner.zip` from the bench
   (`https://YOUR-BENCH-URL/runner.zip`) or copy the repo's `runner/`
   directory to `~/.w2/runner/`.
3. **Environment**: create `~/.w2/env` (then `chmod 600 ~/.w2/env`):
   ```
   W2_SERVER=https://YOUR-BENCH-URL
   W2APP_TOKEN=YOUR-TOKEN
   GEMINI_API_KEY=ORG-KEY
   # CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-...   (if you used setup-token)
   ```
4. **Service**:
   - macOS: copy `examples/com.zennify.w2runner.plist` to
     `~/Library/LaunchAgents/`, edit paths, `launchctl load` it.
   - Linux/WSL: copy `examples/w2-runner.service` to
     `~/.config/systemd/user/`, then
     `systemctl --user enable --now w2-runner`.
5. **Verify**: `python3 ~/.w2/runner/w2_runner.py --selfcheck` → all PASS,
   and the console shows your runner connected.

## Using it (weekly, per deal)

- Upload the deal's BRD + two SDDs (or one, for a review). That's your whole
  job; hands-free is the default.
- **Keep your laptop awake until the run finishes** (typically 15–30
  minutes). If it sleeps, nothing is lost — the run pauses and resumes when
  you're back; the console will say "waiting for your runner".
- Your seat pays only for **your** runs (owner-pays affinity); a colleague's
  evaluation never draws on your credit, and yours never draws on theirs.
- Rough budget: one comparative evaluation ≈ 350–480k input tokens on your
  seat — comfortable weekly headroom alongside normal Claude use. Check
  `claude /status` if curious; the run page shows exact per-judge usage.

## The safety rails you're running under

The runner **refuses to start** if an `ANTHROPIC_API_KEY` is anywhere in
scope, refuses settings that could inject one, proves subscription auth
before doing any work, and **halts instantly** if any call ever reports a
billable API cost — the bench independently rejects such a result too. The
line to trust in the console: *reported API cost $0.00 (must stay 0.00)*.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Self-check: "G1: ANTHROPIC_API_KEY is set" | `unset ANTHROPIC_API_KEY` and remove it from your shell profile; the runner will not run beside an API key, by design |
| Self-check: G3 preflight failed | `claude login` again with your Team seat, or re-run `claude setup-token`; confirm your seat has Claude Code access |
| Console: 401 / token prompt loops | Token typo or revoked — re-copy from the administrator |
| Console: "waiting for your runner" forever | Laptop asleep, service not running (`systemctl --user status w2-runner` / launchctl list), or corporate proxy blocking the bench URL |
| Gemini self-check: free-tier refused | Expected — free tier may train on data and excludes commercial use. Use the org's paid key |
| BILLING_TRIPWIRE error on a run | The rails worked. Fix credentials (subscription only) and start a new run; nothing was billed silently |
| Reinstall / new laptop | Just run the Option A command again — the installer is idempotent |

## What this setup deliberately does not do

It does not log you in inside the web app — Anthropic scopes subscription
credentials to Claude Code and claude.ai, so the login happens on your
machine, in your browser, on Anthropic's page. It does not pool the team's
tokens (Team-plan credit is per seat). And it never, under any configuration,
touches the Claude API meter.
