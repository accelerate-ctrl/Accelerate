import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, Sparkles, Trash2, Check, Brain } from 'lucide-react';
import { Link } from 'react-router-dom';
import { apiGet, apiPost, type Suggestion, type SuggestionStats } from '@/lib/api';

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

      <ul className="space-y-2">
        {items?.map((s) => (
          <li key={s.id} className="bg-white rounded-lg border border-zen-light-green/40 p-3">
            <div className="flex items-start gap-2">
              <CheckCircle2 size={14} className="text-zen-teal mt-0.5" />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className={`text-[10px] uppercase rounded px-1.5 py-0.5 ${STATUS_BADGE[s.status]}`}>{s.status}</span>
                  <span className="font-mono text-[10px] text-zen-dark-teal/60">{s.kind}</span>
                  {s.target && (
                    <Link to={`/subcap?id=${encodeURIComponent(s.target)}`} className="font-mono text-[10px] bg-zen-light-green/50 text-zen-dark-teal px-1 rounded hover:text-zen-dark-green">
                      {s.target}
                    </Link>
                  )}
                  <span className="text-sm font-medium text-zen-dark-green">{s.title}</span>
                </div>
                <div className="text-xs text-zen-dark-teal mt-1">{s.rationale}</div>
                <div className="text-[10px] text-zen-dark-teal/60 mt-1 flex items-center gap-2">
                  <Link to={`/reasoning-chain?id=${encodeURIComponent(s.chain_id)}`} className="inline-flex items-center gap-0.5 text-zen-teal hover:text-zen-dark-teal">
                    <Brain size={10} /> chain {s.chain_id.slice(-6)}
                  </Link>
                  <span>· gate {s.gate_overall}</span>
                  <span>· {new Date(s.created_at).toLocaleString()}</span>
                  {s.decided_by && <span>· by {s.decided_by}</span>}
                </div>
              </div>
              {s.status === 'pending' && (
                <div className="flex gap-1">
                  <button
                    onClick={() => apply.mutate(s.id)}
                    className="bg-zen-teal hover:bg-zen-dark-teal text-white text-[10px] px-2 py-1 rounded inline-flex items-center gap-0.5"
                  >
                    <Check size={10} /> Apply
                  </button>
                  <button
                    onClick={() => reject.mutate(s.id)}
                    className="bg-zen-orange/80 hover:bg-zen-orange text-white text-[10px] px-2 py-1 rounded inline-flex items-center gap-0.5"
                  >
                    <Trash2 size={10} /> Reject
                  </button>
                </div>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
