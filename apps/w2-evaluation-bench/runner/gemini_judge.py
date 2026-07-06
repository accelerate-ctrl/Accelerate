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


# Free-tier markers in Google error payloads (quota ids / messages). The API
# exposes no clean "tier" field, so detection is BEST-EFFORT and the policy is
# FAIL-CLOSED (PRD D8, TRD TR-10, errata Q3): a positively-detected free-tier
# key is refused; an unverifiable key is refused UNLESS the operator declares
# the tier (W2_GEMINI_TIER=paid — the installer writes this for the verified
# org key) or sets the pilot override W2_ALLOW_GEMINI_FREE_TIER=1.
_FREE_TIER_MARKERS = ("freetier", "free_tier", "free tier",
                      "generaterequestsperminuteperprojectpermodel-freetier")


def _probe_tier(key: str, model: str) -> str:
    """'free' on a positive free-tier signal, else 'unverified'. One
    ~1-output-token probe call; quota errors carry the clearest tier signal."""
    body = {"contents": [{"parts": [{"text": "OK"}]}],
            "generationConfig": {"maxOutputTokens": 1}}
    req = urllib.request.Request(
        ENDPOINT.format(model=model, key=key),
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            payload = r.read().decode()
    except Exception as e:
        payload = (getattr(e, "read", lambda: b"")().decode(errors="replace")
                   if hasattr(e, "read") else str(e))
    low = payload.lower()
    if any(m in low for m in _FREE_TIER_MARKERS):
        return "free"
    return "unverified"


def preflight() -> dict:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise GeminiJudgeError(
            "GEMINI_API_KEY is not set. Create a key in Google AI Studio "
            "(paid tier for client/commercial material — free-tier prompts may "
            "be used for training) and export it for panel mode.")
    declared = os.environ.get("W2_GEMINI_TIER", "").strip().lower()
    allow_free = os.environ.get("W2_ALLOW_GEMINI_FREE_TIER") == "1"
    if declared == "paid":
        return {"gemini_model": DEFAULT_MODEL, "tier": "paid (declared)"}
    tier = _probe_tier(key, DEFAULT_MODEL)
    if tier == "free" and not allow_free:
        raise GeminiJudgeError(
            "GEMINI_API_KEY appears to be a FREE-TIER key (quota metadata "
            "matched the free tier). Free-tier prompts may be used for "
            "training and commercial use is excluded — client SDDs must not "
            "run on it. Use the org's paid-tier key (set W2_GEMINI_TIER=paid "
            "once verified), or for non-client pilots only set "
            "W2_ALLOW_GEMINI_FREE_TIER=1.")
    if tier == "unverified" and not allow_free:
        raise GeminiJudgeError(
            "Could not verify the GEMINI_API_KEY's billing tier. This bench "
            "fails closed on tier uncertainty (client material must never run "
            "on a training-eligible free key): set W2_GEMINI_TIER=paid after "
            "confirming the key is billed (the installer writes this for the "
            "org key), or for non-client pilots set W2_ALLOW_GEMINI_FREE_TIER=1.")
    return {"gemini_model": DEFAULT_MODEL,
            "tier": "free (allowed by override)" if tier == "free" else tier}


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
