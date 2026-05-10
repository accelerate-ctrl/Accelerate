"""LLM router — model dispatch + cache + cost tracker integration.

Routing matrix (per spec §3 / ARCHITECTURE ADR-0004):

    GEMINI_FLASH  → cheap claim extraction + adversarial first-pass
    GEMINI_PRO    → mid-cost synthesis + multi-step reasoning
    SONNET        → high-quality reasoning, adversarial critic, suggestions
    OPUS          → quarterly digest + breaking-change adjudication

In dev (``llm_live_mode=False``) every model resolves to a deterministic
canned-response adapter keyed off SHA256(model + prompt + temperature).
That keeps tests hermetic + reproducible.

Cost is tracked via :class:`CostTracker` (BigQuery in prod, JSON-backed
repository in dev).  Cache is a content-hash keyed read-through layer.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ...config import get_settings
from .cache import LlmCache
from .cost_tracker import BudgetExceeded, CostTracker  # noqa: F401 (re-exported)

logger = logging.getLogger(__name__)


class ModelKind(str, Enum):
    GEMINI_FLASH = "gemini-flash"
    GEMINI_PRO = "gemini-pro"
    SONNET = "sonnet"
    OPUS = "opus"


# Approximate $/1M token blended pricing (in/out averaged).  Used by the
# CostTracker dev-mode estimator.  Prod will read live billing data.
PRICE_PER_M_TOKENS: dict[ModelKind, float] = {
    ModelKind.GEMINI_FLASH: 0.30,
    ModelKind.GEMINI_PRO: 3.50,
    ModelKind.SONNET: 6.00,
    ModelKind.OPUS: 30.00,
}


@dataclass(frozen=True)
class LlmRequest:
    model: ModelKind
    prompt: str
    system: str | None = None
    temperature: float = 0.0
    max_tokens: int = 1024
    cache: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LlmResponse:
    text: str
    model: ModelKind
    cached: bool
    input_tokens: int
    output_tokens: int
    cost_usd: float
    finish_reason: str = "stop"
    raw: dict[str, Any] | None = None


def _approx_tokens(text: str) -> int:
    """Cheap proxy for token counts in dev-mode (~4 chars/token)."""
    return max(1, len(text) // 4)


_SOURCE_BLOCK_RX = re.compile(
    r"^\[(?P<id>[A-Za-z0-9_\-:.]+)\]\s*\([^)]+\)\s*(?P<title>[^\n]*)\n(?P<body>.*?)(?=^\[|\Z)",
    re.MULTILINE | re.DOTALL,
)
_SUBCAP_RX = re.compile(r"\bP[1-4]C\d+\.\d+(?:\.\d+)?\b")


def _parsed_sources(prompt: str) -> list[tuple[str, str]]:
    """Pull (source_id, lowercased_text) pairs out of the consultant prompt."""
    out: list[tuple[str, str]] = []
    for m in _SOURCE_BLOCK_RX.finditer(prompt):
        out.append((m.group("id"), (m.group("title") + " " + m.group("body")).lower()))
    return out


def _pick_subcap(prompt: str, fallback: str = "P1C1.1.1") -> str:
    m = _SUBCAP_RX.search(prompt)
    return m.group(0) if m else fallback


# Each candidate claim is (claim_text, must-overlap keywords used to find a
# matching source).  At least 2 keywords have to appear in the source body
# for the hallucination gate to call the citation supported.
_CANDIDATES: list[tuple[str, list[str]]] = [
    ("digital strategy document banking retail authoring", ["digital", "strategy"]),
    ("regulatory change management compliance program", ["regulatory", "compliance"]),
    ("composable banking architecture core launches", ["composable", "banking"]),
    ("generative ai assistant for strategy authoring", ["genai", "strategy"]),
]


def _claims_from_evidence(prompt: str) -> dict:
    """Build claims + citations rooted in real source IDs from the prompt.

    The hallucination + citation gates require:
        1. every claim's source IDs appear in the consultant-loop source list
        2. the cited source body shares ≥2 salient tokens with the claim text

    We pick claim/source pairs that satisfy both, falling back to a single
    generic claim when nothing matches.
    """
    sources = _parsed_sources(prompt)
    subcap = _pick_subcap(prompt)
    if not sources:
        return {"claims": [{"text": "no evidence available", "subcap_id": subcap, "sources": [], "confidence": 0.1}]}

    claims: list[dict] = []
    for claim_text, keywords in _CANDIDATES:
        # find a source whose body contains all the keywords
        match = next(
            (sid for sid, body in sources if all(k in body for k in keywords)),
            None,
        )
        if match:
            claims.append({
                "text": claim_text,
                "subcap_id": subcap,
                "sources": [match],
                "confidence": 0.78,
            })
        if len(claims) == 2:
            break
    if not claims:
        # generic fallback — cite the first source even if overlap is weak
        sid, _ = sources[0]
        claims.append({"text": "evidence sketch", "subcap_id": subcap, "sources": [sid], "confidence": 0.4})
    return {"claims": claims}


def _suggestions_from_subcap(prompt: str) -> dict:
    subcap = _pick_subcap(prompt)
    return {
        "suggestions": [
            {
                "kind": "add_use_case",
                "target": subcap,
                "title": f"GenAI co-author for {subcap}",
                "rationale": "Internal SOWs + recent analyst trends both call out an AI assistant for this artifact.",
            }
        ]
    }


def _dev_mode_text(req: LlmRequest) -> str:
    """Return a deterministic canned response.

    The shape mimics the consultant loop's expected outputs so tests don't
    need to special-case dev-mode.  The Anthropic + Vertex adapters return
    the same content type (free-form text) — the consultant loop is
    responsible for parsing.
    """
    sys = (req.system or "").lower()
    p = req.prompt.lower()

    # Order matters — suggestion + adversarial dispatch come before claim
    # extraction because their prompts often quote earlier "claims" output.
    if "suggest" in sys or "suggest concrete catalogue" in p or '"suggestions"' in p:
        return json.dumps(_suggestions_from_subcap(req.prompt))
    if "adversari" in sys or "critique" in p or "red team" in sys:
        return (
            '{"verdict":"weak","issues":['
            '{"claim_idx":0,"issue":"citation does not directly support the claim",'
            '"severity":"medium"}],"score":0.6}'
        )
    if "extract claims" in p or "extract claims" in sys or ("evidence:" in p and "claims" in p):
        return json.dumps(_claims_from_evidence(req.prompt))
    if "gate" in sys or "validat" in p:
        return '{"verdict":"pass","reasoning":"all citations resolve and claims fit schema"}'
    # generic fall-through (digest fragments etc)
    return (
        f"[dev-mode {req.model.value}] "
        f"prompt={req.prompt[:120].replace(chr(10), ' ')}…"
    )


# ─── Adapters ───────────────────────────────────────────────────────────────

def _call_dev(req: LlmRequest) -> LlmResponse:
    text = _dev_mode_text(req)
    return LlmResponse(
        text=text,
        model=req.model,
        cached=False,
        input_tokens=_approx_tokens((req.system or "") + req.prompt),
        output_tokens=_approx_tokens(text),
        cost_usd=0.0,
        raw={"adapter": "dev"},
    )


def _call_anthropic(req: LlmRequest) -> LlmResponse:
    """Anthropic adapter — imported lazily so dev-mode never needs the SDK."""
    s = get_settings()
    if not s.anthropic_api_key:
        raise RuntimeError("anthropic_api_key not set; cannot call Anthropic in live mode")
    import anthropic  # type: ignore[import-not-found]

    client = anthropic.Anthropic(api_key=s.anthropic_api_key)
    model_id = (
        s.anthropic_model_sonnet
        if req.model == ModelKind.SONNET
        else s.anthropic_model_opus
    )
    msg = client.messages.create(
        model=model_id,
        max_tokens=req.max_tokens,
        temperature=req.temperature,
        system=req.system or "",
        messages=[{"role": "user", "content": req.prompt}],
    )
    text = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")
    in_tok = getattr(msg.usage, "input_tokens", 0)
    out_tok = getattr(msg.usage, "output_tokens", 0)
    cost = (in_tok + out_tok) / 1_000_000 * PRICE_PER_M_TOKENS[req.model]
    return LlmResponse(
        text=text,
        model=req.model,
        cached=False,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost_usd=cost,
        finish_reason=str(msg.stop_reason or "stop"),
        raw={"adapter": "anthropic", "model_id": model_id},
    )


def _call_vertex(req: LlmRequest) -> LlmResponse:
    """Vertex Gemini adapter — lazy import."""
    s = get_settings()
    if not s.gcp_project_id:
        raise RuntimeError("gcp_project_id not set; cannot call Vertex in live mode")
    from vertexai.generative_models import GenerativeModel  # type: ignore[import-not-found]
    import vertexai  # type: ignore[import-not-found]

    vertexai.init(project=s.gcp_project_id, location=s.vertex_region)
    model_id = (
        s.gemini_model_flash
        if req.model == ModelKind.GEMINI_FLASH
        else s.gemini_model_pro
    )
    model = GenerativeModel(model_id, system_instruction=req.system)
    resp = model.generate_content(
        req.prompt,
        generation_config={
            "temperature": req.temperature,
            "max_output_tokens": req.max_tokens,
        },
    )
    text = resp.text or ""
    usage = getattr(resp, "usage_metadata", None)
    in_tok = getattr(usage, "prompt_token_count", _approx_tokens(req.prompt))
    out_tok = getattr(usage, "candidates_token_count", _approx_tokens(text))
    cost = (in_tok + out_tok) / 1_000_000 * PRICE_PER_M_TOKENS[req.model]
    return LlmResponse(
        text=text,
        model=req.model,
        cached=False,
        input_tokens=in_tok,
        output_tokens=out_tok,
        cost_usd=cost,
        raw={"adapter": "vertex", "model_id": model_id},
    )


# ─── Router entry-point ─────────────────────────────────────────────────────

_cache = LlmCache()
_tracker = CostTracker()


def call(req: LlmRequest) -> LlmResponse:
    """Dispatch to the right adapter, with cache + cost guardrails.

    Order of operations:
        1. Cache lookup (if req.cache).
        2. Cost-tracker pre-check — raises BudgetExceeded if the daily
           ceiling is already hit.
        3. Adapter dispatch.
        4. Cache write + cost-tracker record.
    """
    if req.cache:
        hit = _cache.get(req)
        if hit is not None:
            return LlmResponse(**{**hit.__dict__, "cached": True})

    s = get_settings()
    _tracker.assert_within_budget()

    if not s.llm_live_mode:
        resp = _call_dev(req)
    elif req.model in (ModelKind.SONNET, ModelKind.OPUS):
        resp = _call_anthropic(req)
    else:
        resp = _call_vertex(req)

    if req.cache:
        _cache.put(req, resp)
    _tracker.record(req.model, resp.input_tokens, resp.output_tokens, resp.cost_usd)
    return resp


def reset_state_for_tests() -> None:
    """Clear the module-level cache + cost tracker (test fixture only)."""
    _cache.clear()
    _tracker.clear()
