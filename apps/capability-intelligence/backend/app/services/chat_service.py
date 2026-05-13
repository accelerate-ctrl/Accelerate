"""RAG Chat — embed query → vector search → LLM call with citations.

Per spec §12 / ARCHITECTURE Batch 8.

Pipeline
========

    user prompt
        │
        ▼
    embeddings.embed_text(prompt) (Batch 4)
        │
        ▼
    VectorStore.search(prompt, k=8)  → news / trends / SOWs / stories
        │
        ▼
    structured retrieval: also pull recent reasoning chains for the
    detected subcap (regex P1C1.1.1) so the answer can cite the loop's
    grounded claims.
        │
        ▼
    consultant_loop.run(synth=GEMINI_PRO) with the assembled evidence
        │
        ▼
    Reply with claims + cited source IDs; persisted to
    chat_conversations as a message turn.

Conversation memory: at most 10 most-recent turns are passed back into
the next prompt so multi-turn context survives. Beyond 10 we summarise
to keep token budget bounded.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from .repository import get_repository

logger = logging.getLogger(__name__)

CONVERSATIONS_COLLECTION = "chat_conversations"
MAX_HISTORY_TURNS = 10
DEFAULT_TOP_K = 8

_SUBCAP_RX = re.compile(r"\bP[1-4]C\d+\.\d+(?:\.\d+)?\b")


@dataclass
class ChatTurn:
    role: str  # "user" | "assistant"
    text: str
    citations: list[str] = field(default_factory=list)
    chain_id: str | None = None
    cost_usd: float = 0.0
    sources: list[dict] = field(default_factory=list)
    created_at: str = ""
    # Populated only on assistant turns where the consultant loop raised.
    # Lets the SPA show "Anthropic key invalid (stage=synthesize)" instead
    # of the generic "Lookup failed" string.
    error: dict | None = None


@dataclass
class ChatReply:
    conversation_id: str
    message_id: str
    reply: str
    citations: list[str]
    chain_id: str | None
    cost_usd: float
    sources: list[dict]
    error: dict | None = None


# ─── Helpers ────────────────────────────────────────────────────────────────


def _extract_subcap(text: str) -> str | None:
    m = _SUBCAP_RX.search(text)
    return m.group(0) if m else None


def _retrieve(query: str, *, top_k: int = DEFAULT_TOP_K) -> list[dict]:
    """Pull semantic + structured evidence rows the chat LLM can cite.

    Grounding sources (in priority order):
      * Vector store (subcaps, SOWs, stories, news, trends)
      * SOW mentions for the named subcap
      * Lifecycle row for the named subcap
      * Recent news_items with `impact` (Batch 2)
      * Recent trend_clusters labels + summaries (Batch 2)
      * Pending suggestions (Batch 6) — what the AI has already proposed
      * Partner releases (Batch 3) — what partners are shipping
    """
    from .llm.vector_store import VectorStore

    sources: list[dict] = []
    vs = VectorStore()
    if vs.size() > 0:
        for hit in vs.search(query, k=top_k):
            sources.append({
                "id": hit.doc_id,
                "kind": hit.metadata.get("kind", "vector"),
                "title": hit.metadata.get("title", hit.doc_id),
                "text": hit.text[:1200],
                "score": round(hit.score, 4),
                "url": hit.metadata.get("url"),
            })

    repo = get_repository()
    sub_cap_id = _extract_subcap(query)

    if sub_cap_id:
        # Per-subcap evidence: SOW mentions + lifecycle row.
        for sow_mention in repo.list("sow_mentions"):
            if sow_mention.get("sub_cap_id") != sub_cap_id:
                continue
            sources.append({
                "id": sow_mention.get("mention_id") or f"sow-{sow_mention.get('sow_id')}-{sub_cap_id}",
                "kind": "sow_mention",
                "title": f"SOW {sow_mention.get('sow_id')}",
                "text": sow_mention.get("excerpt", ""),
            })
        lifecycle = repo.get("lifecycle_scores", sub_cap_id)
        if lifecycle:
            sources.append({
                "id": f"lifecycle-{sub_cap_id}",
                "kind": "lifecycle",
                "title": f"Lifecycle for {sub_cap_id}",
                "text": (
                    f"State {lifecycle.get('state')} score {lifecycle.get('score')} "
                    f"confidence {lifecycle.get('confidence')}; signals: "
                    f"{lifecycle.get('signals')}"
                ),
            })
        # News items whose impact synthesis named this subcap.
        for n in repo.list("news_items"):
            impact = n.get("impact") or {}
            if sub_cap_id in (impact.get("affects_subcaps") or []):
                sources.append({
                    "id": n.get("id"),
                    "kind": "news_impact",
                    "title": n.get("title"),
                    "text": (impact.get("summary") or n.get("text") or "")[:600],
                    "url": n.get("url"),
                })

    # Recent news_items + trend_clusters (cap to 4 each so the prompt
    # stays bounded; matched by keyword overlap with the query).
    qtokens = {t.lower() for t in query.replace(",", " ").split() if len(t) > 3}
    if qtokens:
        ranked_news = []
        for n in repo.list("news_items"):
            blob = (n.get("title") or "") + " " + (n.get("text") or "")
            hits = sum(1 for t in qtokens if t in blob.lower())
            if hits:
                ranked_news.append((hits, n))
        ranked_news.sort(key=lambda r: (-r[0], -(r[1].get("published_at") or "")))
        for _h, n in ranked_news[:4]:
            sources.append({
                "id": n.get("id"),
                "kind": "news",
                "title": n.get("title"),
                "text": (n.get("text") or "")[:600],
                "url": n.get("url"),
            })
        ranked_trends = []
        for c in repo.list("trend_clusters"):
            blob = (c.get("label") or "") + " " + (c.get("summary") or "")
            hits = sum(1 for t in qtokens if t in blob.lower())
            if hits:
                ranked_trends.append((hits, c))
        ranked_trends.sort(key=lambda r: -r[0])
        for _h, c in ranked_trends[:3]:
            sources.append({
                "id": c.get("cluster_id"),
                "kind": "trend",
                "title": c.get("label"),
                "text": c.get("summary"),
            })

    # Pending suggestions that target the named subcap or its L1.
    if sub_cap_id:
        for s in repo.list("suggestions"):
            if s.get("status") != "pending":
                continue
            if s.get("target") == sub_cap_id:
                sources.append({
                    "id": s.get("id"),
                    "kind": "suggestion",
                    "title": s.get("title"),
                    "text": s.get("rationale") or "",
                })

    # Partner releases that map to the named subcap's L1.
    if sub_cap_id:
        sc = repo.get("subcaps", sub_cap_id) or {}
        l1 = sc.get("l1_capability")
        if l1:
            for rel in repo.list("partner_releases"):
                hits = [f for f in (rel.get("features") or []) if f.get("mapped_l1") == l1]
                if hits:
                    sources.append({
                        "id": rel.get("release_id"),
                        "kind": "partner_release",
                        "title": f"{rel.get('partner_name')}: {rel.get('title')}",
                        "text": "; ".join(f.get("feature") for f in hits)[:600],
                        "url": rel.get("url"),
                    })

    return sources


def _trim_history(turns: list[dict]) -> list[dict]:
    if len(turns) <= MAX_HISTORY_TURNS:
        return turns
    # Keep the first system-style turn (if any) + the last N-1 turns
    head = turns[:1] if turns and turns[0].get("role") == "system" else []
    return head + turns[-(MAX_HISTORY_TURNS - len(head)):]


def _conversation_doc_id(conversation_id: str) -> str:
    return conversation_id


# ─── Public API ─────────────────────────────────────────────────────────────


def list_conversations(limit: int = 50) -> list[dict]:
    items = list(get_repository().list(CONVERSATIONS_COLLECTION))
    items.sort(key=lambda c: c.get("updated_at", ""), reverse=True)
    return items[:limit]


def get_conversation(conversation_id: str) -> dict | None:
    return get_repository().get(CONVERSATIONS_COLLECTION, conversation_id)


def post_message(
    *,
    message: str,
    conversation_id: str | None = None,
    persist: bool = True,
) -> ChatReply:
    """Run a single chat round-trip.

    Returns the reply + citations + back-pointer to the consultant chain
    that produced it (so the UI can deep-link to Reasoning Chain Viewer).
    """
    from .consultant_loop import run as run_loop
    from .llm.router import ModelKind

    repo = get_repository()
    now = datetime.now(timezone.utc).isoformat()

    convo = (
        repo.get(CONVERSATIONS_COLLECTION, conversation_id)
        if conversation_id
        else None
    )
    if not convo:
        conversation_id = conversation_id or f"chat-{uuid4().hex[:12]}"
        convo = {
            "conversation_id": conversation_id,
            "created_at": now,
            "updated_at": now,
            "turns": [],
        }

    user_turn = ChatTurn(role="user", text=message, created_at=now)
    convo["turns"].append(asdict(user_turn))
    convo["turns"] = _trim_history(convo["turns"])

    sources = _retrieve(message)
    sub_cap_id = _extract_subcap(message)

    history_blob = "\n".join(
        f"[{t.get('role')}] {(t.get('text') or '')[:300]}"
        for t in convo["turns"][-MAX_HISTORY_TURNS:]
    )
    query = (
        "Conversation so far:\n" + history_blob + "\n\n"
        "Answer the user's latest message using the cited evidence. "
        "Format citations as [<source_id>] inline."
    )

    try:
        loop = run_loop(
            query=query,
            sub_cap_id=sub_cap_id,
            synth_model=ModelKind.GEMINI_PRO,
            persist=True,
        )
        # Assemble reply text from claim outputs (or fall back to raw answer)
        claims = loop.output.get("claims") or []
        if claims:
            reply_text = " ".join(c.get("text", "").strip() for c in claims).strip()
            cited = sorted({sid for c in claims for sid in (c.get("sources") or [])})
        else:
            reply_text = (
                f"I matched {len(sources)} source(s) but couldn't extract grounded claims. "
                "Try a more specific question or mention a sub_cap_id like P1C1.1.1."
            )
            cited = []
        chain_id = loop.chain_id
        cost = loop.total_cost_usd
    except Exception as exc:  # noqa: BLE001
        logger.warning("chat consultant_loop failed: %s", exc)
        # Find which step we were in by looking at the latest persisted chain
        # (the loop persists each step as it goes).
        from .consultant_loop import list_chains as _list_chains
        latest_chain = _list_chains(sub_cap_id=sub_cap_id, limit=1)
        stage = None
        if latest_chain:
            steps = latest_chain[0].get("steps") or []
            stage = (steps[-1] or {}).get("name") if steps else None
        err = {
            "error_type": type(exc).__name__,
            "stage": stage or "unknown",
            "detail": str(exc)[:400],
            "hint": (
                "Check /api/ready → llm.adapters for credential health, then "
                "rotate the Secret Manager secret and redeploy if needed."
            ),
        }
        reply_text = (
            f"The {stage or 'consultant'} step failed: {type(exc).__name__}. "
            "See diagnostic block below — and the QA & Audit Dashboard for "
            "the persisted reasoning chain."
        )
        cited = []
        chain_id = None
        cost = 0.0
    else:
        err = None

    assistant_turn = ChatTurn(
        role="assistant",
        text=reply_text,
        citations=cited,
        chain_id=chain_id,
        cost_usd=cost,
        sources=sources,
        created_at=datetime.now(timezone.utc).isoformat(),
        error=err,
    )
    convo["turns"].append(asdict(assistant_turn))
    convo["updated_at"] = assistant_turn.created_at

    if persist:
        repo.upsert(CONVERSATIONS_COLLECTION, conversation_id, convo)

    message_id = f"msg-{uuid4().hex[:10]}"
    return ChatReply(
        conversation_id=conversation_id,
        message_id=message_id,
        reply=reply_text,
        citations=cited,
        chain_id=chain_id,
        cost_usd=cost,
        sources=sources,
        error=err,
    )
