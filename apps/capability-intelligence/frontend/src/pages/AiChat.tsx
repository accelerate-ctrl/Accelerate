import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Brain, Send, MessageSquare, ExternalLink, DollarSign } from 'lucide-react';
import { Link } from 'react-router-dom';
import { apiGet, apiPost, type ChatConversation, type ChatReply } from '@/lib/api';

export default function AiChat() {
  const qc = useQueryClient();
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [draft, setDraft] = useState('Tell me about P1C1.1.1 — what are its top SOWs?');
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const { data: list } = useQuery<ChatConversation[]>({
    queryKey: ['chat-list'],
    queryFn: () => apiGet<ChatConversation[]>('/chat?limit=50'),
  });

  const { data: convo } = useQuery<ChatConversation>({
    queryKey: ['chat', conversationId],
    enabled: !!conversationId,
    queryFn: () => apiGet<ChatConversation>(`/chat/${encodeURIComponent(conversationId || '')}`),
  });

  const send = useMutation({
    mutationFn: () =>
      apiPost<ChatReply>('/chat/messages', {
        message: draft,
        conversation_id: conversationId || undefined,
      }),
    onSuccess: (r) => {
      setConversationId(r.conversation_id);
      setDraft('');
      qc.invalidateQueries();
    },
  });

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [convo?.turns?.length]);

  const turns = convo?.turns || [];
  const totalCost = turns.reduce((acc, t) => acc + (t.cost_usd || 0), 0);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-zen-dark-green">AI Chat</h1>
        <p className="text-sm text-zen-dark-teal/80">
          RAG over the catalogue + Batch-3 SOWs + Batch-4 news + Batch-6 lifecycle.
          Mention a subcap ID (e.g. <span className="font-mono">P1C1.1.1</span>) to anchor retrieval.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <div className="lg:col-span-1 bg-white rounded-lg border border-zen-light-green/40 p-3">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-xs uppercase font-semibold tracking-wider text-zen-dark-green">
              Conversations
            </h2>
            <button
              onClick={() => setConversationId(null)}
              className="text-[10px] text-zen-teal hover:text-zen-dark-teal underline"
            >
              new chat
            </button>
          </div>
          <ul className="divide-y divide-zen-light-green/30 max-h-[640px] overflow-auto">
            {(list || []).map((c) => {
              const last = c.turns[c.turns.length - 1];
              return (
                <li key={c.conversation_id}>
                  <button
                    onClick={() => setConversationId(c.conversation_id)}
                    className={`w-full text-left p-2 rounded hover:bg-zen-white-green/60 ${conversationId === c.conversation_id ? 'bg-zen-white-green' : ''}`}
                  >
                    <div className="flex items-center gap-2 text-xs">
                      <MessageSquare size={12} className="text-zen-teal" />
                      <span className="font-mono text-[10px] text-zen-dark-teal/70">
                        {c.conversation_id.slice(-6)}
                      </span>
                    </div>
                    <div className="text-[10px] text-zen-dark-teal mt-0.5 truncate">
                      {last?.text?.slice(0, 80) || '(empty)'}
                    </div>
                    <div className="text-[9px] text-zen-dark-teal/60 mt-0.5">
                      {new Date(c.updated_at).toLocaleString()} · {c.turns.length} turns
                    </div>
                  </button>
                </li>
              );
            })}
            {(list || []).length === 0 && (
              <li className="text-xs text-zen-dark-teal/60 italic py-2">
                No conversations yet — type a message below.
              </li>
            )}
          </ul>
        </div>

        <div className="lg:col-span-2 bg-white rounded-lg border border-zen-light-green/40 p-3 flex flex-col h-[640px]">
          <div className="flex items-center gap-2 text-xs text-zen-dark-teal/70 mb-2">
            <Brain size={14} className="text-zen-teal" />
            <span>{conversationId ? `chat ${conversationId.slice(-6)}` : 'new chat'}</span>
            {totalCost > 0 && (
              <span className="ml-auto inline-flex items-center gap-0.5">
                <DollarSign size={10} /> {totalCost.toFixed(4)}
              </span>
            )}
          </div>
          <div ref={scrollRef} className="flex-1 overflow-auto space-y-2 pr-1">
            {turns.length === 0 && (
              <div className="text-xs text-zen-dark-teal/60 italic">
                Start the conversation by typing a question below.
              </div>
            )}
            {turns.map((t, i) => (
              <div
                key={i}
                className={`rounded-lg p-2 text-xs ${t.role === 'user' ? 'bg-zen-light-green/30 ml-8' : 'bg-zen-white-green/70 mr-8'}`}
              >
                <div className="flex items-center gap-2 text-[10px] text-zen-dark-teal/70">
                  <span className="uppercase font-mono">{t.role}</span>
                  {t.cost_usd != null && t.cost_usd > 0 && (
                    <span className="ml-auto">${t.cost_usd.toFixed(4)}</span>
                  )}
                </div>
                <div className="text-zen-dark-teal mt-1 whitespace-pre-wrap">{t.text}</div>
                {(t.citations || []).length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {(t.citations || []).map((c) => (
                      <span key={c} className="font-mono text-[10px] bg-zen-teal/30 text-zen-dark-green rounded px-1">
                        {c}
                      </span>
                    ))}
                  </div>
                )}
                {(t.sources || []).length > 0 && t.role === 'assistant' && (
                  <details className="mt-1">
                    <summary className="text-[10px] text-zen-teal hover:text-zen-dark-teal cursor-pointer">
                      {(t.sources || []).length} sources retrieved
                    </summary>
                    <ul className="mt-1 space-y-0.5">
                      {(t.sources || []).slice(0, 6).map((s) => (
                        <li key={s.id} className="text-[10px] text-zen-dark-teal">
                          <span className="font-mono text-[10px] bg-zen-light-green/40 rounded px-1 mr-1">{s.kind}</span>
                          {s.title || s.id}
                          {s.url && (
                            <a href={s.url} target="_blank" rel="noreferrer" className="ml-1 text-zen-teal">
                              <ExternalLink size={9} className="inline" />
                            </a>
                          )}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
                {t.chain_id && (
                  <Link
                    to={`/reasoning?id=${encodeURIComponent(t.chain_id)}`}
                    className="text-[10px] text-zen-teal hover:text-zen-dark-teal mt-1 inline-flex items-center gap-0.5"
                  >
                    <Brain size={9} /> chain {t.chain_id.slice(-6)}
                  </Link>
                )}
              </div>
            ))}
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (draft.trim()) send.mutate();
            }}
            className="mt-2 flex items-center gap-1"
          >
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Type a message…"
              className="flex-1 border border-zen-light-green rounded px-2 py-1 text-xs"
            />
            <button
              type="submit"
              disabled={send.isPending || !draft.trim()}
              className="bg-zen-teal hover:bg-zen-dark-teal text-white text-xs px-3 py-1 rounded disabled:opacity-50"
            >
              <Send size={12} className={`inline mr-1 ${send.isPending ? 'animate-pulse' : ''}`} />
              {send.isPending ? 'Thinking…' : 'Send'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
