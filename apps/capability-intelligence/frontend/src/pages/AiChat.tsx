import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  Brain,
  DollarSign,
  ExternalLink,
  MessageSquare,
  Plus,
  RefreshCw,
  Send,
} from 'lucide-react';
import { apiGet, apiPostStream, type ChatConversation } from '@/lib/api';
import ReasoningChainMini, { type ChainSummary } from '@/components/ReasoningChainMini';

// ─── Local stream-state shape ───────────────────────────────────────────────
// As the SSE stream advances we update this in-place so the UI can render
// each phase live without losing earlier events.

type StreamSource = { id: string; kind: string; title: string; url?: string };
type ChatError = { error_type: string; stage: string; detail: string; hint?: string };

type StreamState = {
  draftUser: string;
  phase: 'idle' | 'retrieving' | 'reasoning' | 'replying' | 'done';
  sources: StreamSource[];
  reply: string;
  citations: string[];
  cost: number;
  chainId: string | null;
  error: ChatError | null;
};

const INITIAL_STREAM: StreamState = {
  draftUser: '',
  phase: 'idle',
  sources: [],
  reply: '',
  citations: [],
  cost: 0,
  chainId: null,
  error: null,
};

// Per-source-kind chip colour (uses the canonical ZDS palette).
const KIND_CHIP: Record<string, string> = {
  subcap: 'bg-zen-light-green/60 text-zen-dark-teal',
  sow_mention: 'bg-zen-ice text-zen-dark-teal',
  story: 'bg-zen-purple-grey/40 text-zen-text-gray',
  news: 'bg-zen-light-blue/30 text-zen-blue',
  news_impact: 'bg-zen-light-blue/40 text-zen-blue',
  trend: 'bg-zen-light-orange/50 text-zen-orange',
  suggestion: 'bg-zen-light-green/70 text-zen-dark-teal',
  partner_release: 'bg-zen-mint/60 text-zen-dark-green',
  lifecycle: 'bg-zen-light-green/40 text-zen-dark-teal',
  vector: 'bg-zen-ice text-zen-text-gray',
};

export default function AiChat() {
  const qc = useQueryClient();
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [draft, setDraft] = useState('Tell me about P1C1.1.1 — what are its top SOWs?');
  const [stream, setStream] = useState<StreamState>(INITIAL_STREAM);
  const [streaming, setStreaming] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const { data: list } = useQuery<ChatConversation[]>({
    queryKey: ['chat-list'],
    queryFn: () => apiGet<ChatConversation[]>('/chat?limit=50'),
  });
  const { data: convo } = useQuery<ChatConversation>({
    queryKey: ['chat', conversationId],
    enabled: !!conversationId,
    queryFn: () =>
      apiGet<ChatConversation>(`/chat/${encodeURIComponent(conversationId || '')}`),
  });

  // Active reasoning chain (loaded for the most recent assistant turn).
  const lastTurn = convo?.turns?.[convo.turns.length - 1];
  const activeChainId = stream.chainId || lastTurn?.chain_id || null;
  const { data: chain } = useQuery<ChainSummary>({
    queryKey: ['chat-chain', activeChainId],
    queryFn: () =>
      apiGet<ChainSummary>(`/reasoning-chains/${encodeURIComponent(activeChainId || '')}`),
    enabled: !!activeChainId,
  });

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [convo?.turns?.length, stream.phase, stream.reply]);

  async function send() {
    if (!draft.trim() || streaming) return;
    setStreaming(true);
    setStream({
      ...INITIAL_STREAM,
      draftUser: draft,
      phase: 'retrieving',
    });
    const userQuery = draft;
    setDraft('');
    try {
      for await (const ev of apiPostStream('/chat/messages/stream', {
        message: userQuery,
        conversation_id: conversationId || undefined,
      })) {
        if (ev.event === 'retrieve') {
          const data = ev.data as { sources: StreamSource[] };
          setStream((s) => ({
            ...s,
            phase: 'reasoning',
            sources: data.sources || [],
          }));
        } else if (ev.event === 'chain') {
          const data = ev.data as { chain_id: string; cost_usd: number };
          setStream((s) => ({
            ...s,
            chainId: data.chain_id,
            cost: data.cost_usd,
          }));
        } else if (ev.event === 'reply') {
          const data = ev.data as {
            reply: string;
            citations: string[];
            cost_usd: number;
            error: ChatError | null;
          };
          setStream((s) => ({
            ...s,
            phase: 'replying',
            reply: data.reply,
            citations: data.citations || [],
            cost: data.cost_usd,
            error: data.error,
          }));
        } else if (ev.event === 'done') {
          const data = ev.data as { conversation_id: string };
          setConversationId(data.conversation_id);
          setStream((s) => ({ ...s, phase: 'done' }));
          qc.invalidateQueries({ queryKey: ['chat-list'] });
          qc.invalidateQueries({ queryKey: ['chat', data.conversation_id] });
        }
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setStream((s) => ({
        ...s,
        phase: 'done',
        error: {
          error_type: 'StreamError',
          stage: 'transport',
          detail: msg,
          hint: 'Check /api/ready → llm.adapters for credential health.',
        },
      }));
    } finally {
      setStreaming(false);
    }
  }

  const turns = convo?.turns || [];
  const totalCost =
    turns.reduce((acc, t) => acc + (t.cost_usd || 0), 0) + stream.cost;

  return (
    <div className="space-y-4 h-full">
      <div>
        <h1 className="text-2xl font-semibold text-zen-dark-green">AI Chat</h1>
        <p className="text-sm text-zen-dark-teal/80 max-w-3xl">
          Grounded over the catalogue, SOWs, stories, news, trends, partner releases, and
          pending suggestions. Mention a subcap ID (e.g.{' '}
          <span className="font-mono">P1C1.1.1</span>) to anchor retrieval. Every reply carries
          its reasoning chain inline so you can audit the 7-step process.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-3 h-[calc(100vh-220px)] min-h-[480px]">
        {/* LEFT: conversation list */}
        <div className="bg-white rounded-lg border border-zen-separator p-3 flex flex-col overflow-hidden order-2 lg:order-1">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-[10px] uppercase font-semibold tracking-wider text-zen-text-gray">
              Conversations
            </h2>
            <button
              type="button"
              onClick={() => setConversationId(null)}
              className="text-[10px] inline-flex items-center gap-0.5 text-zen-teal hover:text-zen-dark-teal"
            >
              <Plus size={11} /> New
            </button>
          </div>
          <ul className="divide-y divide-zen-separator/40 overflow-auto flex-1">
            {(list || []).map((c) => {
              const last = c.turns[c.turns.length - 1];
              const isActive = conversationId === c.conversation_id;
              return (
                <li key={c.conversation_id}>
                  <button
                    onClick={() => setConversationId(c.conversation_id)}
                    className={`w-full text-left p-2 rounded transition-colors ${
                      isActive ? 'bg-zen-ice' : 'hover:bg-zen-ice/40'
                    }`}
                  >
                    <div className="flex items-center gap-2 text-[11px]">
                      <MessageSquare size={11} className="text-zen-teal" />
                      <span className="font-mono text-[10px] text-zen-muted-text">
                        {c.conversation_id.slice(-6)}
                      </span>
                    </div>
                    <div className="text-xs text-zen-dark-green mt-0.5 line-clamp-2">
                      {last?.text?.slice(0, 80) || '(empty)'}
                    </div>
                    <div className="text-[9px] text-zen-muted-text mt-0.5">
                      {new Date(c.updated_at).toLocaleString()} · {c.turns.length} turns
                    </div>
                  </button>
                </li>
              );
            })}
            {(list || []).length === 0 && (
              <li className="text-xs text-zen-muted-text italic py-2 px-1">
                No conversations yet. Type a question below to start one.
              </li>
            )}
          </ul>
          {totalCost > 0 && (
            <div className="mt-2 border-t border-zen-separator pt-2 flex items-center justify-between text-[10px] text-zen-text-gray">
              <span className="inline-flex items-center gap-0.5">
                <DollarSign size={10} /> total
              </span>
              <span className="font-mono">${totalCost.toFixed(4)}</span>
            </div>
          )}
        </div>

        {/* RIGHT: thread + composer */}
        <div className="bg-white rounded-lg border border-zen-separator flex flex-col overflow-hidden order-1 lg:order-2 min-h-[420px]">
          <div className="flex items-center gap-2 text-xs text-zen-text-gray border-b border-zen-separator px-3 py-2">
            <Brain size={14} className="text-zen-teal" />
            <span>{conversationId ? `chat ${conversationId.slice(-6)}` : 'new chat'}</span>
            {streaming && (
              <span className="inline-flex items-center gap-1 ml-auto text-zen-teal">
                <RefreshCw size={12} className="animate-spin" />
                {stream.phase === 'retrieving' && 'Retrieving evidence…'}
                {stream.phase === 'reasoning' && 'Reasoning…'}
                {stream.phase === 'replying' && 'Writing reply…'}
              </span>
            )}
          </div>

          <div ref={scrollRef} className="flex-1 overflow-auto p-3 space-y-3">
            {turns.length === 0 && stream.phase === 'idle' && (
              <div className="text-xs text-zen-muted-text italic">
                Start the conversation by typing a question below. Try{' '}
                <span className="font-mono">Tell me about P1C1.1.1</span>.
              </div>
            )}

            {/* Persisted turns */}
            {turns.map((t, i) => (
              <ChatBubble key={i} turn={t} kindChip={KIND_CHIP} />
            ))}

            {/* Live in-flight turn — shown only while streaming */}
            {streaming || stream.phase !== 'idle' ? (
              <>
                {stream.draftUser && (
                  <ChatBubble
                    turn={{
                      role: 'user',
                      text: stream.draftUser,
                      cost_usd: 0,
                      citations: [],
                      sources: [],
                      created_at: new Date().toISOString(),
                    }}
                    kindChip={KIND_CHIP}
                  />
                )}
                {(stream.sources.length > 0 || stream.reply || stream.error) && (
                  <ChatBubble
                    turn={{
                      role: 'assistant',
                      text: stream.reply || (streaming ? '…' : ''),
                      citations: stream.citations,
                      sources: stream.sources,
                      cost_usd: stream.cost,
                      created_at: new Date().toISOString(),
                      chain_id: stream.chainId,
                      error: stream.error || undefined,
                    }}
                    kindChip={KIND_CHIP}
                    chain={chain ?? null}
                  />
                )}
              </>
            ) : null}

            {/* Reasoning chain for the LAST persisted assistant turn */}
            {!streaming && lastTurn?.role === 'assistant' && chain && (
              <div className="border-t border-zen-separator pt-2 mt-1">
                <div className="text-[10px] uppercase tracking-wider text-zen-muted-text mb-1">
                  Reasoning chain (last reply)
                </div>
                <ReasoningChainMini chain={chain} />
              </div>
            )}
          </div>

          {/* Composer */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              send();
            }}
            className="border-t border-zen-separator p-2 flex items-center gap-2"
          >
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Ask a question — mention a subcap ID to anchor retrieval"
              className="flex-1 border border-zen-separator rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-zen-teal"
              disabled={streaming}
            />
            <button
              type="submit"
              disabled={streaming || !draft.trim()}
              className="bg-zen-teal hover:bg-zen-dark-teal text-white text-xs px-3 py-1.5 rounded transition-colors duration-200 disabled:opacity-50 inline-flex items-center gap-1"
            >
              <Send size={12} className={streaming ? 'animate-pulse' : ''} />
              {streaming ? 'Thinking…' : 'Send'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

type BubbleTurn = {
  role: string;
  text: string;
  citations?: string[];
  sources?: { id: string; kind?: string; title?: string; url?: string | null }[];
  cost_usd?: number;
  created_at?: string;
  chain_id?: string | null;
  error?: ChatError;
};

function ChatBubble({
  turn,
  kindChip,
  chain,
}: {
  turn: BubbleTurn;
  kindChip: Record<string, string>;
  chain?: ChainSummary | null;
}) {
  const isUser = turn.role === 'user';
  return (
    <div
      className={`rounded-lg p-3 text-sm border ${
        isUser
          ? 'bg-zen-light-green/30 ml-6 md:ml-12 border-zen-light-green/60'
          : 'bg-white border-zen-separator'
      }`}
    >
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-zen-muted-text">
        <span className="font-mono">{turn.role}</span>
        {typeof turn.cost_usd === 'number' && turn.cost_usd > 0 && (
          <span className="ml-auto">${turn.cost_usd.toFixed(4)}</span>
        )}
      </div>
      <div className="text-zen-dark-green mt-1 whitespace-pre-wrap leading-relaxed">
        {turn.text || (
          <span className="text-zen-muted-text italic">(no reply text)</span>
        )}
      </div>

      {/* Citation chips (the IDs the model cited inline). */}
      {(turn.citations || []).length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {(turn.citations || []).map((c) => (
            <span
              key={c}
              className="font-mono text-[10px] bg-zen-teal/20 text-zen-dark-green rounded px-1.5 py-0.5"
            >
              [{c}]
            </span>
          ))}
        </div>
      )}

      {/* Per-source citation cards. */}
      {turn.role === 'assistant' && (turn.sources || []).length > 0 && (
        <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-1.5">
          {(turn.sources || []).slice(0, 8).map((s) => (
            <div
              key={s.id}
              className="border border-zen-separator rounded p-1.5 text-[11px] bg-zen-ice/40"
            >
              <div className="flex items-baseline gap-1.5">
                <span
                  className={`text-[9px] font-mono rounded px-1 ${kindChip[s.kind || 'vector'] || 'bg-zen-ice text-zen-text-gray'}`}
                >
                  {s.kind || 'vector'}
                </span>
                {s.url && (
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noreferrer"
                    className="ml-auto text-zen-teal hover:text-zen-dark-teal"
                  >
                    <ExternalLink size={9} />
                  </a>
                )}
              </div>
              <div className="text-zen-dark-green truncate" title={s.title}>
                {s.title || s.id}
              </div>
            </div>
          ))}
          {(turn.sources || []).length > 8 && (
            <div className="text-[10px] text-zen-muted-text italic">
              + {(turn.sources || []).length - 8} more sources
            </div>
          )}
        </div>
      )}

      {/* Error diagnostic block — fired when consultant loop raised. */}
      {turn.error && (
        <div className="mt-2 border border-zen-orange/40 bg-zen-light-orange/30 rounded p-2 text-[11px]">
          <div className="flex items-center gap-1 font-semibold text-zen-orange mb-1">
            <AlertTriangle size={12} />
            <span>
              {turn.error.error_type} at <span className="font-mono">{turn.error.stage}</span>
            </span>
          </div>
          <div className="text-zen-dark-green">{turn.error.detail}</div>
          {turn.error.hint && (
            <div className="text-zen-text-gray italic mt-1">{turn.error.hint}</div>
          )}
        </div>
      )}

      {/* Reasoning chain widget (shown on assistant turn when chain prop is set). */}
      {!isUser && chain && (
        <div className="mt-2">
          <ReasoningChainMini chain={chain} />
        </div>
      )}
    </div>
  );
}
