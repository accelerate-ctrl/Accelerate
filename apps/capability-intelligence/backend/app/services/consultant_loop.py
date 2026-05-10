"""7-step consultant loop.

Per spec §5 / ARCHITECTURE Batch 4.  Given a *task* (e.g. "audit subcap
P1C1.1.1 against current evidence + propose suggestions"), the loop:

    1. CLARIFY        — pin scope (subcap, sub_vertical, time window)
    2. RETRIEVE_INT   — vector + structured query of SOWs, stories, KG
    3. RETRIEVE_EXT   — vector + freshness query of news + trends
    4. SYNTHESIZE     — LLM call (router pick) → claims + suggestions
    5. ADVERSARIAL    — Sonnet (or dev-mode rule) red-teams the output
    6. GATE           — 8-gate validation engine
    7. FINALIZE       — write reasoning chain + suggestions; route to UI

Every step is appended to a reasoning chain row in
``reasoning_chains`` with inputs / outputs / model / cost.  The chain is
the auditable record shown on the Reasoning Chain Viewer page.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .llm.router import LlmRequest, ModelKind, call as llm_call
from .llm.vector_store import VectorStore
from .repository import get_repository
from .validation_gates_service import GateRun, run_gates

logger = logging.getLogger(__name__)

CHAIN_COLLECTION = "reasoning_chains"
SUGGESTION_COLLECTION = "suggestions"


@dataclass
class ChainStep:
    name: str
    started_at: str
    completed_at: str
    model: str | None = None
    input_summary: str = ""
    output_summary: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    cached: bool = False
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class LoopResult:
    chain_id: str
    sub_cap_id: str | None
    started_at: str
    completed_at: str
    steps: list[ChainStep]
    output: dict
    sources: list[dict]
    suggestions: list[dict]
    gates: dict
    overall: str  # "pass" | "warn" | "fail"
    total_cost_usd: float


# ─── Step helpers ───────────────────────────────────────────────────────────


def _step(name: str) -> tuple[ChainStep, datetime]:
    started = datetime.now(timezone.utc)
    return ChainStep(name=name, started_at=started.isoformat(), completed_at=""), started


def _finish(step: ChainStep) -> ChainStep:
    step.completed_at = datetime.now(timezone.utc).isoformat()
    return step


def _retrieve_internal(sub_cap_id: str | None, query: str) -> list[dict]:
    """Pull SOW chunks / stories / mentions tied to the subcap."""
    repo = get_repository()
    sources: list[dict] = []

    # SOW mentions for this subcap (Batch 3)
    mentions = repo.list("sow_mentions")
    if sub_cap_id:
        mentions = [m for m in mentions if m.get("sub_cap_id") == sub_cap_id]
    for m in mentions[:10]:
        sources.append({
            "id": m.get("mention_id") or f"sow-{m.get('sow_id')}-{sub_cap_id}",
            "kind": "sow_mention",
            "title": f"SOW {m.get('sow_id')} – {sub_cap_id or 'subcap'}",
            "text": m.get("excerpt", ""),
            "ingested_at": m.get("ingested_at"),
        })

    # Canonical stories
    stories = [
        s for s in repo.list("stories_canonical")
        if not sub_cap_id or s.get("sub_cap_id") == sub_cap_id
    ]
    for st in stories[:10]:
        sources.append({
            "id": st.get("story_key") or f"story-{st.get('id')}",
            "kind": "story",
            "title": st.get("summary", "")[:160],
            "text": (st.get("description") or st.get("ac_text") or "")[:1200],
            "ingested_at": st.get("ingested_at"),
        })

    # Vector hits (catches anything indexed but not directly tied to subcap)
    vs = VectorStore()
    if vs.size() > 0:
        for hit in vs.search(query, k=5):
            sources.append({
                "id": hit.doc_id,
                "kind": hit.metadata.get("kind", "vector"),
                "title": hit.metadata.get("title", hit.doc_id),
                "text": hit.text[:1200],
                "score": round(hit.score, 4),
                "url": hit.metadata.get("url"),
                "ingested_at": hit.metadata.get("ingested_at"),
            })
    return sources


def _retrieve_external(query: str) -> list[dict]:
    """Pull news + trends — both via repo and vector retrieval."""
    repo = get_repository()
    items: list[dict] = []
    for kind, coll in (("news", "news_items"), ("trend", "trends_items")):
        for item in sorted(
            repo.list(coll), key=lambda r: r.get("published_at", ""), reverse=True,
        )[:5]:
            items.append({
                "id": item["id"],
                "kind": kind,
                "title": item.get("title"),
                "text": item.get("text", "")[:1200],
                "url": item.get("url"),
                "published_at": item.get("published_at"),
                "ingested_at": item.get("ingested_at"),
            })
    return items


def _synthesize(query: str, sources: list[dict], model: ModelKind) -> tuple[dict, "LlmResponse"]:
    """Call router, parse JSON, fall back to raw text on parse error."""
    src_block = "\n".join(
        f"[{s['id']}] ({s.get('kind')}) {s.get('title', '')}\n{s.get('text', '')[:400]}"
        for s in sources[:12]
    )
    prompt = (
        f"Task: {query}\n\n"
        f"Evidence:\n{src_block}\n\n"
        "Return JSON with key 'claims': a list of {text, subcap_id, sources, confidence}."
    )
    resp = llm_call(LlmRequest(
        model=model,
        prompt=prompt,
        system="You are a Zennify capability-intelligence consultant. Extract claims grounded in the cited evidence. JSON only.",
        max_tokens=1500,
    ))
    try:
        parsed = json.loads(resp.text)
    except Exception:
        parsed = {"claims": [], "raw": resp.text}
    return parsed, resp


def _adversarial(output: dict, sources: list[dict]) -> tuple[dict, "LlmResponse"]:
    """Sonnet-class red-team review (dev-mode resolves to a canned critique)."""
    prompt = (
        "Critique the following extracted claims against the cited evidence. "
        "Return JSON {verdict: pass|weak|fail, issues:[{claim_idx, issue, severity}], score: 0..1}.\n\n"
        f"Claims:\n{json.dumps(output.get('claims', []), indent=2)}\n\n"
        f"Sources:\n{json.dumps([{ 'id':s['id'],'title':s.get('title',''),'text':s.get('text','')[:300]} for s in sources], indent=2)}"
    )
    resp = llm_call(LlmRequest(
        model=ModelKind.SONNET,
        prompt=prompt,
        system="You are a skeptical adversarial reviewer.  Be specific.  JSON only.",
        max_tokens=1000,
    ))
    try:
        parsed = json.loads(resp.text)
    except Exception:
        parsed = {"verdict": "weak", "issues": [], "score": 0.5, "raw": resp.text}
    return parsed, resp


def _propose_suggestions(output: dict, sub_cap_id: str | None) -> tuple[list[dict], "LlmResponse"]:
    prompt = (
        "Given these grounded claims, suggest concrete catalogue edits. "
        "Return JSON {suggestions:[{kind, target, title, rationale}]}.  "
        "Allowed kinds: add_use_case, refine_subcap, add_theme, "
        "rename_subcap, merge_use_case, split_subcap, delete_subcap.\n\n"
        f"sub_cap_id: {sub_cap_id or '(unscoped)'}\n"
        f"Claims: {json.dumps(output.get('claims', []))}"
    )
    resp = llm_call(LlmRequest(
        model=ModelKind.SONNET,
        prompt=prompt,
        system="You suggest targeted catalogue improvements.  JSON only.",
        max_tokens=1000,
    ))
    try:
        parsed = json.loads(resp.text)
        suggestions = parsed.get("suggestions", [])
    except Exception:
        suggestions = []
    return suggestions, resp


# ─── Public entry point ─────────────────────────────────────────────────────


def run(
    *,
    query: str,
    sub_cap_id: str | None = None,
    synth_model: ModelKind = ModelKind.GEMINI_PRO,
    persist: bool = True,
) -> LoopResult:
    chain_id = f"chain-{uuid4().hex[:12]}"
    started = datetime.now(timezone.utc)
    steps: list[ChainStep] = []
    total_cost = 0.0

    # 1) clarify
    s1, _ = _step("clarify")
    s1.input_summary = f"query={query!r} sub_cap_id={sub_cap_id}"
    s1.output_summary = f"sub_cap_id={sub_cap_id} model={synth_model.value}"
    steps.append(_finish(s1))

    # 2) retrieve internal
    s2, _ = _step("retrieve_internal")
    int_sources = _retrieve_internal(sub_cap_id, query)
    s2.output_summary = f"{len(int_sources)} internal sources"
    s2.detail = {"source_ids": [s["id"] for s in int_sources]}
    steps.append(_finish(s2))

    # 3) retrieve external
    s3, _ = _step("retrieve_external")
    ext_sources = _retrieve_external(query)
    s3.output_summary = f"{len(ext_sources)} external sources"
    s3.detail = {"source_ids": [s["id"] for s in ext_sources]}
    steps.append(_finish(s3))

    sources = int_sources + ext_sources

    # 4) synthesize
    s4, _ = _step("synthesize")
    output, synth_resp = _synthesize(query, sources, synth_model)
    s4.model = synth_resp.model.value
    s4.tokens_in = synth_resp.input_tokens
    s4.tokens_out = synth_resp.output_tokens
    s4.cost_usd = synth_resp.cost_usd
    s4.cached = synth_resp.cached
    s4.input_summary = f"{len(sources)} sources"
    s4.output_summary = f"{len(output.get('claims', []))} claims"
    total_cost += synth_resp.cost_usd
    steps.append(_finish(s4))

    # 5) adversarial
    s5, _ = _step("adversarial")
    adv, adv_resp = _adversarial(output, sources)
    s5.model = adv_resp.model.value
    s5.tokens_in = adv_resp.input_tokens
    s5.tokens_out = adv_resp.output_tokens
    s5.cost_usd = adv_resp.cost_usd
    s5.cached = adv_resp.cached
    s5.output_summary = f"verdict={adv.get('verdict')} score={adv.get('score', 0)}"
    s5.detail = {"adversarial": adv}
    total_cost += adv_resp.cost_usd
    steps.append(_finish(s5))

    # 5b) suggestions (synth model)
    s5b, _ = _step("propose_suggestions")
    suggestions, sug_resp = _propose_suggestions(output, sub_cap_id)
    s5b.model = sug_resp.model.value
    s5b.tokens_in = sug_resp.input_tokens
    s5b.tokens_out = sug_resp.output_tokens
    s5b.cost_usd = sug_resp.cost_usd
    s5b.cached = sug_resp.cached
    s5b.output_summary = f"{len(suggestions)} suggestion(s)"
    total_cost += sug_resp.cost_usd
    steps.append(_finish(s5b))

    # 6) gate
    s6, _ = _step("gate")
    gate_run: GateRun = run_gates(
        output,
        sources,
        suggestions=suggestions,
        recent_outputs=_recent_outputs(sub_cap_id),
    )
    s6.output_summary = f"overall={gate_run.overall} score={gate_run.score:.2f}"
    s6.detail = gate_run.to_dict()
    steps.append(_finish(s6))

    # 7) finalize
    s7, _ = _step("finalize")
    completed = datetime.now(timezone.utc)
    s7.output_summary = f"chain_id={chain_id} cost=${total_cost:.4f}"
    steps.append(_finish(s7))

    result = LoopResult(
        chain_id=chain_id,
        sub_cap_id=sub_cap_id,
        started_at=started.isoformat(),
        completed_at=completed.isoformat(),
        steps=steps,
        output=output,
        sources=sources,
        suggestions=suggestions,
        gates=gate_run.to_dict(),
        overall=gate_run.overall,
        total_cost_usd=total_cost,
    )

    if persist:
        _persist(result)

    return result


def _recent_outputs(sub_cap_id: str | None) -> list[dict]:
    repo = get_repository()
    chains = repo.list(CHAIN_COLLECTION)
    if sub_cap_id:
        chains = [c for c in chains if c.get("sub_cap_id") == sub_cap_id]
    chains.sort(key=lambda c: c.get("started_at", ""), reverse=True)
    return [c.get("output", {}) for c in chains[:30]]


def _persist(result: LoopResult) -> None:
    repo = get_repository()
    repo.upsert(
        CHAIN_COLLECTION,
        result.chain_id,
        {
            **{k: v for k, v in asdict(result).items() if k != "steps"},
            "steps": [asdict(s) for s in result.steps],
        },
    )
    # Stage suggestions in the suggestions collection w/ status=pending
    for i, sug in enumerate(result.suggestions):
        sid = f"sug-{result.chain_id}-{i}"
        repo.upsert(
            SUGGESTION_COLLECTION,
            sid,
            {
                "id": sid,
                "chain_id": result.chain_id,
                "sub_cap_id": result.sub_cap_id,
                "kind": sug.get("kind"),
                "target": sug.get("target"),
                "title": sug.get("title"),
                "rationale": sug.get("rationale"),
                "status": "pending",  # pending | applied | rejected
                "gate_overall": result.overall,
                "created_at": result.completed_at,
            },
        )


def list_chains(sub_cap_id: str | None = None, limit: int = 50) -> list[dict]:
    chains = get_repository().list(CHAIN_COLLECTION)
    if sub_cap_id:
        chains = [c for c in chains if c.get("sub_cap_id") == sub_cap_id]
    chains.sort(key=lambda c: c.get("started_at", ""), reverse=True)
    return chains[:limit]


def get_chain(chain_id: str) -> dict | None:
    return get_repository().get(CHAIN_COLLECTION, chain_id)
