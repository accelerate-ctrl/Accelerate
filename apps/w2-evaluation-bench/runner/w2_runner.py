#!/usr/bin/env python3
"""w2_runner — the operator-side execution agent.

Runs as a background daemon on operator-controlled compute, polling the W2
server (local or Cloud Run) for open work packets and executing each act of
model judgment under YOUR Claude subscription (interactive `claude login` or a
`claude setup-token` CLAUDE_CODE_OAUTH_TOKEN) — never an Anthropic API key.

    python3 w2_runner.py --server https://<cloud-run-url> --token $W2APP_TOKEN
    python3 w2_runner.py --server ... --engine panel --gemini-passes 4,5
    python3 w2_runner.py --server http://localhost:8787 --engine mock --once

Engines:
  claude-code  (default) `claude -p` per packet under the billing guard
               (refuses API keys, preflights subscription auth, trips on any
               billable cost, ledgers token usage).
  panel        Multi-LLM judge: Claude Code executes every packet EXCEPT the
               scoring passes listed in --gemini-passes (default 4,5), which
               are judged by Gemini via GEMINI_API_KEY (Google-side billing;
               zero Claude API spend). Cross-model disagreement surfaces
               honestly in the five-pass stddev/ICC statistics.
  mock         Deterministic built-in intelligence for demos/CI.

The default loop runs forever with exponential backoff on server outages —
install it once (see examples/w2-runner.service) and forget it; --once drains
the current queue and exits (CI/cron style).
"""
from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys
import time
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default=os.environ.get("W2_SERVER",
                                                       "http://localhost:8787"))
    ap.add_argument("--engine", choices=("claude-code", "panel", "mock"),
                    default="claude-code")
    ap.add_argument("--token", default=os.environ.get("W2APP_TOKEN", ""),
                    help="shared secret for the server's X-W2-Token auth")
    ap.add_argument("--gemini-passes", default="4,5",
                    help="panel mode: scoring pass numbers judged by Gemini")
    ap.add_argument("--once", action="store_true", help="drain current packets then exit")
    ap.add_argument("--poll", type=float, default=3.0)
    args = ap.parse_args()
    runner_id = f"runner-{uuid.uuid4().hex[:8]}"
    gemini_passes = {int(x) for x in args.gemini_passes.split(",") if x.strip()}

    global _TOKEN
    _TOKEN = args.token
    claude_exe = None
    if args.engine in ("claude-code", "panel"):
        info = billing_guard.preflight()  # G1+G2+G3
        claude_exe = info["claude"]
        print(f"[{runner_id}] billing guard PASS — subscription auth confirmed, "
              f"no API keys in scope. Engine: {claude_exe}")
        if args.engine == "panel":
            import gemini_judge
            gj = gemini_judge.preflight()
            print(f"[{runner_id}] panel mode — Gemini co-judge "
                  f"({gj['gemini_model']}) takes scoring passes "
                  f"{sorted(gemini_passes)}; Google-side billing, "
                  "zero Claude API spend.")
    else:
        import mock_intelligence  # noqa: F401
        print(f"[{runner_id}] MOCK engine — no model calls will be made.")

    idle = 0
    backoff = args.poll
    while True:
        try:
            p = http("GET", f"{args.server}/api/packets/next?runner_id={runner_id}")
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
        print(f"[{runner_id}] executing {run_id} :: {pid} ({p['kind']})")
        try:
            if args.engine == "mock":
                import mock_intelligence
                result, usage = mock_intelligence.execute(p), {"engine": "mock"}
            elif (args.engine == "panel" and p.get("kind") == "pass"
                  and int((p.get("meta") or {}).get("pass_n", 0)) in gemini_passes):
                import gemini_judge
                result, usage = gemini_judge.execute(p)
            else:
                result, usage = run_claude_code(p, claude_exe)
                usage["judge"] = "claude-code"
            resp = http("POST", f"{args.server}/api/packets/{run_id}/{urllib.parse.quote(pid, safe='')}/result",
                        {"result": result, "usage": usage})
            print(f"[{runner_id}]   -> stored; run status {resp.get('status')} "
                  f"(in {usage.get('input_tokens')}t / out {usage.get('output_tokens')}t)")
        except billing_guard.BillingGuardError as e:
            print(f"[{runner_id}] !! {e}", file=sys.stderr)
            return 2
        except Exception as e:
            print(f"[{runner_id}] packet {pid} failed: {e}", file=sys.stderr)
            time.sleep(args.poll)


if __name__ == "__main__":
    raise SystemExit(main())
