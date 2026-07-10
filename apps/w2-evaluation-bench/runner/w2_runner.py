#!/usr/bin/env python3
"""w2_runner — the operator-side execution agent (v2.0 dual-judge).

Runs as a background daemon on operator-controlled compute, polling the W2
server (local or Cloud Run) for open work packets and executing each act of
model judgment under YOUR Claude subscription (interactive `claude login` or a
`claude setup-token` CLAUDE_CODE_OAUTH_TOKEN) — never an Anthropic API key.

    python3 w2_runner.py --server https://<cloud-run-url> --token $W2APP_TOKEN
    python3 w2_runner.py --server http://localhost:8787 --engine mock --once
    python3 w2_runner.py --selfcheck   # G1-G3 + Gemini + server reachability

Engines:
  panel        (default) The v2.0 dual-judge panel: packets route by
               meta.judge — claude-code -> `claude -p` under the billing
               guard; gemini -> the Gemini API (GEMINI_API_KEY, Google-side
               billing; zero Claude API spend). Reconciliation, narratives,
               extraction and evidence packets run on Claude (Judge A).
               There is NO silent fallback between judges (TR-8): a missing
               judge refuses at preflight, and mid-run judge failures leave
               packets open rather than mislabel provenance.
  claude-code  Single-judge legacy engine for EVAL_PROTOCOL=five-pass
               regression runs only.
  mock         Deterministic built-in intelligence for demos/CI (judge-aware,
               with seeded divergence so the consensus path is exercised).

The default loop runs forever with exponential backoff on server outages —
install it once (see examples/) and forget it; --once drains the current
queue and exits (CI/cron style).
"""
from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import billing_guard  # noqa: E402


_TOKEN = ""


def http(method: str, url: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if _TOKEN:
        headers["X-W2-Token"] = _TOKEN
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode())


FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_json_reply(text: str) -> dict:
    t = FENCE.sub("", text.strip())
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object in model reply: {t[:200]!r}")
    return json.loads(t[start:end + 1])


def run_claude_code(packet: dict, claude_exe: str) -> tuple[dict, dict]:
    args = [claude_exe, "-p", "--output-format", "json"]
    if not packet.get("needs_web"):
        # Pure-judgment packets need no tools at all; withhold them entirely so
        # the call is a single text completion under the plan credit.
        args += ["--allowed-tools", ""]
    r = subprocess.run(args, input=packet["prompt"], env=billing_guard.scrubbed_env(),
                       capture_output=True, text=True, timeout=3600)
    if r.returncode != 0:
        raise RuntimeError(f"claude -p exit {r.returncode}: {r.stderr[-800:]}")
    payload = json.loads(r.stdout)
    billing_guard.assert_not_billed(payload, packet["packet_id"])  # G4
    result = parse_json_reply(payload.get("result", ""))
    return result, billing_guard.usage_from_result(payload)


# Gemini-only panel (single AI): two model tiers fill the two judge slots —
# genuinely different judges from one provider, one key, no Claude anywhere.
GEMINI_MODEL_A = os.environ.get("W2_GEMINI_MODEL_A", "gemini-2.5-pro")
GEMINI_MODEL_B = os.environ.get("W2_GEMINI_MODEL_B", "gemini-2.5-flash")


def route_judge(packet: dict, engine: str) -> str:
    """TR-8 judge routing. Panel/gemini: pass/review packets go to
    meta.judge (the slot they were addressed to); reconcile, narrative,
    exec_narrative, components, features and evidence are Judge A. No
    silent fallback, ever."""
    if engine not in ("panel", "gemini"):
        return "claude-code"
    meta = packet.get("meta") or {}
    if packet.get("kind") in ("pass", "review") and meta.get("judge"):
        return meta["judge"]
    return "claude-code"


def gemini_model_for(judge_slot: str) -> str:
    """Single-AI mode: Judge A slot -> the deeper Pro tier, Judge B slot ->
    Flash. Two tiers = real methodological divergence, honest consensus."""
    return GEMINI_MODEL_A if judge_slot == "claude-code" else GEMINI_MODEL_B


def selfcheck(server: str, token: str) -> int:
    """TR-31: human-readable PASS/FAIL lines; nonzero exit on any failure.
    Checks the billing guard (G1-G3), the Gemini co-judge credential, and
    bench reachability with the member token."""
    ok = True

    def line(name: str, passed: bool, detail: str) -> None:
        nonlocal ok
        ok = ok and passed
        print(f"[selfcheck] {name:.<24} {'PASS' if passed else 'FAIL'}  ({detail})")

    engine = os.environ.get("W2_ENGINE", "panel")
    if engine == "gemini":
        line("billing guard", True,
             "single-AI Gemini mode — no Claude component; Anthropic "
             "billing surface does not exist")
    else:
        try:
            billing_guard.preflight()
            line("billing guard", True, "no API keys in scope; subscription auth OK")
        except billing_guard.BillingGuardError as e:
            line("billing guard", False, str(e).splitlines()[0][:120])
    try:
        import gemini_judge
        info = gemini_judge.preflight()
        tier = info.get("tier", "unverified")
        line("gemini co-judge", tier != "free",
             f"{info['gemini_model']} ({tier} tier)"
             if tier != "free" else "free tier refused (training/commercial terms)")
    except Exception as e:
        line("gemini co-judge", False, str(e).splitlines()[0][:120])
    global _TOKEN
    _TOKEN = token
    try:
        http("GET", f"{server}/api/runs")
        line("bench reachable", True, f"{server}")
    except urllib.error.HTTPError as e:
        line("bench reachable", False,
             "bad or missing token (401)" if e.code == 401 else f"HTTP {e.code}")
    except Exception as e:
        line("bench reachable", False, str(e)[:120])
    return 0 if ok else 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default=os.environ.get("W2_SERVER",
                                                       "http://localhost:8787"))
    ap.add_argument("--engine", choices=("panel", "gemini", "claude-code", "mock"),
                    default=os.environ.get("W2_ENGINE", "panel"))
    ap.add_argument("--token", default=os.environ.get("W2APP_TOKEN", ""),
                    help="the member's personal bench token (X-W2-Token)")
    ap.add_argument("--once", action="store_true", help="drain current packets then exit")
    ap.add_argument("--poll", type=float, default=3.0)
    ap.add_argument("--selfcheck", action="store_true",
                    help="run G1-G3 + Gemini + reachability checks and exit (TR-31)")
    args = ap.parse_args()
    runner_id = f"runner-{uuid.uuid4().hex[:8]}"

    if args.selfcheck:
        return selfcheck(args.server, args.token)

    global _TOKEN
    _TOKEN = args.token
    claude_exe = None
    if args.engine == "gemini":
        import gemini_judge
        gj = gemini_judge.preflight()
        print(f"[{runner_id}] SINGLE-AI panel — Judge A {GEMINI_MODEL_A}, "
              f"Judge B {GEMINI_MODEL_B} (both Gemini API, Google-side "
              "billing; no Claude component in this mode). Packets route "
              "by meta.judge; no silent fallback between slots.")
    elif args.engine in ("claude-code", "panel"):
        info = billing_guard.preflight()  # G1+G2+G3
        claude_exe = info["claude"]
        print(f"[{runner_id}] billing guard PASS — subscription auth confirmed, "
              f"no API keys in scope. Engine: {claude_exe}")
        if args.engine == "panel":
            import gemini_judge
            gj = gemini_judge.preflight()
            print(f"[{runner_id}] dual-judge panel — Judge A claude-code "
                  f"(subscription), Judge B {gj['gemini_model']} (Gemini API, "
                  "Google-side billing, zero Claude API spend). Packets route "
                  "by meta.judge; no silent fallback between judges.")
    else:
        import mock_intelligence  # noqa: F401
        print(f"[{runner_id}] MOCK engine — no model calls will be made.")

    idle = 0
    backoff = args.poll
    while True:
        try:
            p = http("GET", f"{args.server}/api/packets/next"
                            f"?runner_id={runner_id}&engine={args.engine}")
            backoff = args.poll
        except Exception as e:
            print(f"[{runner_id}] server unreachable ({e}); retrying in "
                  f"{backoff:.0f}s", file=sys.stderr)
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)
            continue
        if not p.get("packet_id"):
            idle += 1
            if args.once and idle >= 2:
                print(f"[{runner_id}] no open packets — done.")
                return 0
            time.sleep(args.poll)
            continue
        idle = 0
        pid, run_id = p["packet_id"], p["run_id"]
        judge = route_judge(p, args.engine)
        print(f"[{runner_id}] executing {run_id} :: {pid} ({p['kind']}"
              + (f" -> {judge}" if args.engine == "panel" else "") + ")")
        try:
            if args.engine == "mock":
                import mock_intelligence
                result = mock_intelligence.execute(p)
                usage = mock_intelligence.usage_for(p)
            elif args.engine == "gemini":
                import gemini_judge
                result, usage = gemini_judge.execute(
                    p, model=gemini_model_for(judge))
                usage["judge"] = judge  # TR-8: report the slot addressed
                usage["engine"] = "gemini"
            elif judge == "gemini":
                import gemini_judge
                result, usage = gemini_judge.execute(p)
            else:
                result, usage = run_claude_code(p, claude_exe)
                usage["judge"] = "claude-code"
            resp = http("POST", f"{args.server}/api/packets/{run_id}/"
                                f"{urllib.parse.quote(pid, safe='')}/result",
                        {"result": result, "usage": usage})
            print(f"[{runner_id}]   -> stored; run status {resp.get('status')} "
                  f"(in {usage.get('input_tokens')}t / out {usage.get('output_tokens')}t)")
        except billing_guard.BillingGuardError as e:
            print(f"[{runner_id}] !! {e}", file=sys.stderr)
            return 2
        except urllib.error.HTTPError as e:
            if e.code == 402:
                # Server-side billing tripwire fired: halt loudly (G4 twin).
                print(f"[{runner_id}] !! server billing tripwire (402) on {pid}: "
                      f"{e.read().decode()[:300]}", file=sys.stderr)
                return 2
            # 400 = malformed result rejected; the packet stays open and a
            # fresh attempt happens on the next poll. Log and continue.
            print(f"[{runner_id}] packet {pid} rejected (HTTP {e.code}): "
                  f"{e.read().decode()[:300]}", file=sys.stderr)
            time.sleep(args.poll)
        except Exception as e:
            print(f"[{runner_id}] packet {pid} failed: {e}", file=sys.stderr)
            time.sleep(args.poll)


if __name__ == "__main__":
    raise SystemExit(main())
