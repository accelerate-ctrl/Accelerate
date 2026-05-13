import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, CheckCircle2, Sparkles, Trash2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import { apiGet, apiPost, type Suggestion, type SuggestionStats } from '@/lib/api';
import ReasoningChainMini, { type ChainSummary } from '@/components/ReasoningChainMini';

const STATUS_BADGE: Record<string, string> = {
  pending: 'bg-zen-light-orange text-zen-dark-green',
  applied: 'bg-zen-teal text-white',
  rejected: 'bg-zen-orange text-white',
};

export default function AiSuggestions() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<'pending' | 'applied' | 'rejected' | ''>('pending');

  const { data: items } = useQuery<Suggestion[]>({
    queryKey: ['suggestions', filter],
    queryFn: () => apiGet<Suggestion[]>(filter ? `/suggestions?status=${filter}` : '/suggestions'),
  });

  const { data: stats } = useQuery<SuggestionStats>({
    queryKey: ['suggestions-stats'],
    queryFn: () => apiGet<SuggestionStats>('/suggestions/stats'),
  });

  const apply = useMutation({
    mutationFn: (sid: string) => apiPost(`/suggestions/${sid}/apply`, {}),
    onSettled: () => qc.invalidateQueries(),
  });

  const reject = useMutation({
    mutationFn: (sid: string) => apiPost(`/suggestions/${sid}/reject`, { reason: 'rejected via UI' }),
    onSettled: () => qc.invalidateQueries(),
  });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-zen-dark-green">AI Suggestions</h1>
        <p className="text-sm text-zen-dark-teal/80">
          Catalogue-edit candidates produced by the 7-step consultant loop. Each suggestion carries
          its reasoning chain + gate verdict; applying queues a diff for review.
        </p>
      </div>

      {stats && (
        <div className="bg-white rounded-lg border border-zen-light-green/40 p-3 text-xs flex items-center gap-3 text-zen-dark-teal">
          <Sparkles size={14} className="text-zen-teal" />
          <span>Total <strong>{stats.total}</strong></span>
          <span>· Pending <strong>{stats.pending}</strong></span>
          <span>· Applied <strong>{stats.applied}</strong></span>
          <span>· Rejected <strong>{stats.rejected}</strong></span>
        </div>
      )}

      <div className="bg-white rounded-lg border border-zen-light-green/40 p-2 flex items-center gap-2 text-xs">
        <span className="text-zen-dark-teal/70">Status</span>
        {(['', 'pending', 'applied', 'rejected'] as const).map((s) => (
          <button
            key={s || 'all'}
            onClick={() => setFilter(s)}
            className={`px-2 py-0.5 rounded ${filter === s ? 'bg-zen-dark-green text-white' : 'bg-zen-light-green/40 text-zen-dark-teal/80'}`}
          >
            {s || 'all'}
          </button>
        ))}
      </div>

      {items && items.length === 0 && (
        <div className="bg-white rounded-lg border border-zen-light-green/40 p-6 text-center text-sm text-zen-dark-teal/70">
          No suggestions for this filter. Trigger a run via{' '}
          <Link to="/reasoning-chain" className="underline text-zen-teal">Reasoning Chain Viewer</Link>.
        </div>
      )}

      <ul className="space-y-3">
        {items?.map((s) => (
          <SuggestionRow
            key={s.id}
            s={s}
            onApply={() => apply.mutate(s.id)}
            onReject={() => reject.mutate(s.id)}
          />
        ))}
      </ul>
    </div>
  );
}

function SuggestionRow({
  s,
  onApply,
  onReject,
}: {
  s: Suggestion;
  onApply: () => void;
  onReject: () => void;
}) {
  // Fetch the chain on-demand so we can show its compressed widget +
  // adversarial review inline. Chain endpoint returns the full chain
  // record including the `steps` array + adversarial step output.
  const { data: chain } = useQuery<ChainSummary & { steps?: Array<{ name: string; detail?: Record<string, unknown> }> }>({
    queryKey: ['chain-mini', s.chain_id],
    queryFn: () => apiGet(`/reasoning-chains/${encodeURIComponent(s.chain_id)}`),
    enabled: !!s.chain_id,
  });

  // Pull the adversarial step out of the chain if present so we can render
  // the AI's self-critique inline — addresses the user's "does the AI
  // challenge its thinking?" complaint.
  const adversarialDetail =
    chain?.steps?.find((st) => st.name === 'adversarial')?.detail || null;
  const critique =
    (adversarialDetail as { critique?: string; severity?: string; weaknesses?: string[] } | null) || null;

  return (
    <li className="bg-white rounded-lg border border-zen-separator p-3">
      <div className="flex items-start gap-2">
        <CheckCircle2 size={14} className="text-zen-teal mt-0.5" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className={`text-[10px] uppercase rounded px-1.5 py-0.5 ${STATUS_BADGE[s.status]}`}
            >
              {s.status}
            </span>
            <span className="font-mono text-[10px] text-zen-muted-text">{s.kind}</span>
            {s.target && (
              <Link
                to={`/subcap?id=${encodeURIComponent(s.target)}`}
                className="font-mono text-[10px] bg-zen-light-green/60 text-zen-dark-teal px-1 rounded hover:text-zen-dark-green"
              >
                {s.target}
              </Link>
            )}
            <span className="text-sm font-medium text-zen-dark-green">{s.title}</span>
          </div>
          <div className="text-xs text-zen-text-gray mt-1">{s.rationale}</div>
          {critique?.critique && (
            <div className="mt-2 border-l-2 border-zen-orange/60 bg-zen-light-orange/20 pl-2 pr-2 py-1.5 rounded-r">
              <div className="text-[10px] uppercase font-semibold text-zen-orange tracking-wider mb-0.5">
                Adversarial self-review
                {critique.severity && (
                  <span className="ml-1 normal-case font-normal text-zen-text-gray">
                    · severity {critique.severity}
                  </span>
                )}
              </div>
              <div className="text-xs text-zen-dark-green">{critique.critique}</div>
              {critique.weaknesses && critique.weaknesses.length > 0 && (
                <ul className="text-[11px] text-zen-text-gray mt-1 list-disc list-inside">
                  {critique.weaknesses.slice(0, 4).map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
          <div className="mt-2">
            <ReasoningChainMini
              chain={
                chain
                  ? { ...chain, total_cost_usd: chain.total_cost_usd, chain_id: s.chain_id }
                  : null
              }
            />
          </div>
          <div className="text-[10px] text-zen-muted-text mt-1.5 flex items-center gap-2">
            <span>gate {s.gate_overall}</span>
            <span>· {new Date(s.created_at).toLocaleString()}</span>
            {s.decided_by && <span>· by {s.decided_by}</span>}
          </div>
        </div>
        {s.status === 'pending' && (
          <div className="flex flex-col gap-1">
            <button
              onClick={onApply}
              className="bg-zen-teal hover:bg-zen-dark-teal text-white text-[10px] px-2 py-1 rounded inline-flex items-center gap-0.5"
            >
              <Check size={10} /> Apply
            </button>
            <button
              onClick={onReject}
              className="bg-zen-orange/80 hover:bg-zen-orange text-white text-[10px] px-2 py-1 rounded inline-flex items-center gap-0.5"
            >
              <Trash2 size={10} /> Reject
            </button>
          </div>
        )}
      </div>
    </li>
  );
}
