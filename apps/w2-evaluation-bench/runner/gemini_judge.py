"""gemini_judge — the second judge of the multi-LLM panel.

Executes a work packet against the Gemini API (Google AI Studio key) so that
designated scoring passes are judged by a DIFFERENT model family than Claude.
Cross-model agreement then becomes part of the evaluation's evidence: the
five-pass stddev/ICC machinery treats a Gemini-scored pass exactly like any
other pass, so model disagreement surfaces honestly as variance instead of
being averaged away silently.

Billing note (kept deliberately separate from the Claude guard): this path
bills GOOGLE, never the Anthropic API. GEMINI_API_KEY is required. The free
tier (Flash models) permits prototyping only — Google may train on free-tier
data and forbids commercial use — so client SDDs require a paid-tier key
(still typically cents per run at Flash pricing). Gemini CLI's consumer-OAuth
route is NOT used here: Google deprecated individual-tier CLI serving in June
2026 and flags third-party OAuth use as abuse; the supported programmatic
surface is this API.
"""
from __future__ import annotations
import json
import os
import re
import urllib.request

DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
ENDPOINT = ("https://generativelanguage.googleapis.com/v1beta/models/"
            "{model}:generateContent?key={key}")


class GeminiJudgeError(RuntimeError):
    pass


def preflight() -> dict:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise GeminiJudgeError(
            "GEMINI_API_KEY is not set. Create a key in Google AI Studio "
            "(paid tier for client/commercial material — free-tier prompts may "
            "be used for training) and export it for panel mode.")
    return {"gemini_model": DEFAULT_MODEL}


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def execute(packet: dict, model: str | None = None, timeout: int = 600) -> tuple[dict, dict]:
    key = os.environ["GEMINI_API_KEY"]
    model = model or DEFAULT_MODEL
    body = {
        "contents": [{"parts": [{"text": packet["prompt"]}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.2,
        },
    }
    req = urllib.request.Request(
        ENDPOINT.format(model=model, key=key),
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        payload = json.loads(r.read().decode())
    try:
        text = "".join(part.get("text", "")
                       for part in payload["candidates"][0]["content"]["parts"])
    except (KeyError, IndexError) as e:
        raise GeminiJudgeError(f"unexpected Gemini response shape: {e}: "
                               f"{json.dumps(payload)[:400]}")
    t = _FENCE.sub("", text.strip())
    start, end = t.find("{"), t.rfind("}")
    if start == -1:
        raise GeminiJudgeError(f"no JSON object in Gemini reply: {t[:200]!r}")
    result = json.loads(t[start:end + 1])
    um = payload.get("usageMetadata") or {}
    usage = {"engine": "gemini", "judge": "gemini", "model": model,
             "input_tokens": um.get("promptTokenCount"),
             "output_tokens": um.get("candidatesTokenCount"),
             # Google-side billing; asserted zero on the CLAUDE-API meter.
             "total_cost_usd": 0.0}
    return result, usage
