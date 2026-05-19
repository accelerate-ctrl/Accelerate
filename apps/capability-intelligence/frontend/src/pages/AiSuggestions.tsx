import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Check,
  CheckCircle2,
  Loader2,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { apiGet, apiPost, type Suggestion, type SuggestionStats } from '@/lib/api';
import ReasoningChainMini, { type ChainSummary } from '@/components/ReasoningChainMini';

const STATUS_BADGE: Record<string, string> = {
  pending: 'bg-zen-light-orange text-zen-dark-green',
  applied: 'bg-zen-teal text-white',
  rejected: 'bg-zen-orange text-white',
};

const ORIGINS = ['loop', 'news', 'partner', 'audit', 'what-if'] as const;
type OriginKey = (typeof ORIGINS)[number];

type OriginsSummary = { origins: Record<string, number> };

export default function AiSuggestions() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<'pending' | 'applied' | 'rejected' | ''>('pending');
  const [originFilter, setOriginFilter] = useState<OriginKey | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkOpen, setBulkOpen] = useState(false);

  const queryUrl = useMemo(() => {
    const p = new URLSearchParams();
    if (filter) p.set('status', filter);
    if (originFilter) p.set('origin', originFilter);
    const qs = p.toString();
    return qs ? `/suggestions?${qs}` : '/suggestions';
  }, [filter, originFilter]);

  const { data: items } = useQuery<Suggestion[]>({
    queryKey: ['suggestions', filter, originFilter],
    queryFn: () => apiGet<Suggestion[]>(queryUrl),
  });

  const { data: stats } = useQuery<SuggestionStats>({
    queryKey: ['suggestions-stats'],
    queryFn: () => apiGet<SuggestionStats>('/suggestions/stats'),
  });

  const { data: originSummary } = useQuery<OriginsSummary>({
    queryKey: ['suggestions-origins'],
    queryFn: () => apiGet<OriginsSummary>('/suggestions/origins'),
  });

  const apply = useMutation({
    mutationFn: (sid: string) => apiPost(`/suggestions/${sid}/apply`, {}),
    onSettled: () => qc.invalidateQueries(),
  });

  const reject = useMutation({
    mutationFn: (sid: string) => apiPost(`/suggestions/${sid}/reject`, { reason: 'rejected via UI' }),
    onSettled: () => qc.invalidateQueries(),
  });

  const bulkReject = useMutation({
    mutationFn: ({ ids, reason }: { ids: string[]; reason: string }) =>
      apiPost('/suggestions/bulk-reject', { ids, reason }),
    onSettled: () => {
      qc.invalidateQueries();
      setSelected(new Set());
      setBulkOpen(false);
    },
  });

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectAllVisible() {
    if (!items) return;
    const pendingIds = items.filter((s) => s.status === 'pending').map((s) => s.id);
    setSelected(new Set(pendingIds));
  }

  function clearSelection() {
    setSelected(new Set());
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-zen-dark-green">AI Suggestions</h1>
        <p className="text-sm text-zen-dark-teal/80">
          Catalogue-edit candidates produced by the 7-step consultant loop. Each suggestion
          carries its reasoning chain + gate verdict; applying queues a diff for review.
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

      <div className="bg-white rounded-lg border border-zen-light-green/40 p-2 flex flex-wrap items-center gap-2 text-xs">
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
        {originSummary && (
          <>
            <span className="text-zen-dark-teal/70 ml-2">Origin</span>
            {ORIGINS.map((o) => {
              const count = originSummary.origins[o] || 0;
              if (count === 0 && originFilter !== o) return null;
              const active = originFilter === o;
              return (
                <button
                  key={o}
                  type="button"
                  onClick={() => setOriginFilter(active ? null : o)}
                  className={`px-2 py-0.5 rounded font-mono text-[10px] ${
                    active ? 'bg-zen-teal text-white' : 'bg-zen-light-green/40 text-zen-dark-teal/80'
                  }`}
                >
                  {o} ({count})
                </button>
              );
            })}
            {originFilter && (
              <button
                type="button"
                onClick={() => setOriginFilter(null)}
                className="text-zen-text-gray hover:text-zen-dark-green underline"
              >
                clear
              </button>
            )}
          </>
        )}
      </div>

      {/* Bulk-action toolbar — only visible when selection is non-empty. */}
      {selected.size > 0 && (
        <div className="bg-zen-light-orange/20 border border-zen-orange/40 rounded-lg p-2 flex flex-wrap items-center gap-2 text-xs">
          <span className="text-zen-dark-green font-medium">
            {selected.size} suggestion{selected.size > 1 ? 's' : ''} selected
          </span>
          <button
            type="button"
            onClick={selectAllVisible}
            className="text-zen-teal hover:text-zen-dark-teal underline"
          >
            Select all visible
          </button>
          <button
            type="button"
            onClick={clearSelection}
            className="text-zen-text-gray hover:text-zen-dark-green underline"
          >
            Clear
          </button>
          <button
            type="button"
            onClick={() => setBulkOpen(true)}
            disabled={bulkReject.isPending}
            className="ml-auto bg-zen-orange text-white px-3 py-1 rounded text-[11px] hover:opacity-90 inline-flex items-center gap-1 disabled:opacity-50"
          >
            {bulkReject.isPending && <Loader2 size={10} className="animate-spin" />}
            Bulk reject…
          </button>
        </div>
      )}

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
            selected={selected.has(s.id)}
            onToggle={() => toggle(s.id)}
            onApply={() => apply.mutate(s.id)}
            onReject={() => reject.mutate(s.id)}
          />
        ))}
      </ul>

      {bulkOpen && (
        <BulkRejectModal
          count={selected.size}
          busy={bulkReject.isPending}
          onCancel={() => setBulkOpen(false)}
          onSubmit={(reason) => bulkReject.mutate({ ids: Array.from(selected), reason })}
        />
      )}
    </div>
  );
}

function SuggestionRow({
  s,
  selected,
  onToggle,
  onApply,
  onReject,
}: {
  s: Suggestion;
  selected: boolean;
  onToggle: () => void;
  onApply: () => void;
  onReject: () => void;
}) {
  const { data: chain } = useQuery<
    ChainSummary & { steps?: Array<{ name: string; detail?: Record<string, unknown> }> }
  >({
    queryKey: ['chain-mini', s.chain_id],
    queryFn: () => apiGet(`/reasoning-chains/${encodeURIComponent(s.chain_id)}`),
    enabled: !!s.chain_id,
  });

  const adversarialDetail =
    chain?.steps?.find((st) => st.name === 'adversarial')?.detail || null;
  const critique =
    (adversarialDetail as { critique?: string; severity?: string; weaknesses?: string[] } | null) || null;

  // IMP-10 — for maturity_descriptor_update suggestions, expose a
  // side-by-side diff between the current text on the subcap and the
  // proposed text in the suggestion's ``proposal_change`` payload.
  const proposalChange =
    (s as unknown as { proposal_change?: { current?: string; proposed?: string; level?: string } })
      .proposal_change || null;
  const showDescriptorDiff =
    s.kind === 'maturity_descriptor_update' &&
    proposalChange &&
    (proposalChange.current || proposalChange.proposed);

  return (
    <li className="bg-white rounded-lg border border-zen-separator p-3">
      <div className="flex items-start gap-2">
        {s.status === 'pending' && (
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggle}
            aria-label={`select suggestion ${s.id}`}
            className="mt-1.5"
          />
        )}
        <CheckCircle2 size={14} className="text-zen-teal mt-0.5" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`text-[10px] uppercase rounded px-1.5 py-0.5 ${STATUS_BADGE[s.status]}`}>
              {s.status}
            </span>
            <span className="font-mono text-[10px] text-zen-muted-text">{s.kind}</span>
            {(s as unknown as { origin?: string }).origin && (
              <span className="font-mono text-[10px] bg-zen-ice text-zen-dark-teal rounded px-1.5 py-0.5">
                {(s as unknown as { origin?: string }).origin}
              </span>
            )}
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
          {showDescriptorDiff && proposalChange && (
            <DescriptorDiff
              current={proposalChange.current || ''}
              proposed={proposalChange.proposed || ''}
              level={proposalChange.level}
            />
          )}
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

/**
 * IMP-10 — Maturity descriptor diff view.
 *
 * Renders a side-by-side current vs proposed comparison so pillar
 * leads don't have to open the Subcap Deep Dive in a separate tab to
 * see what the descriptor currently says.
 */
function DescriptorDiff({
  current,
  proposed,
  level,
}: {
  current: string;
  proposed: string;
  level?: string;
}) {
  return (
    <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
      <div className="bg-zen-light-green/20 border border-zen-light-green/60 rounded p-2">
        <div className="text-[10px] uppercase tracking-wider text-zen-dark-teal/70 mb-1">
          Current{level ? ` · ${level}` : ''}
        </div>
        <div className="text-zen-dark-green whitespace-pre-line">
          {current || <span className="italic text-zen-text-gray">(empty)</span>}
        </div>
      </div>
      <div className="bg-zen-ice border border-zen-teal/40 rounded p-2">
        <div className="text-[10px] uppercase tracking-wider text-zen-teal mb-1">
          Proposed{level ? ` · ${level}` : ''}
        </div>
        <div className="text-zen-dark-green whitespace-pre-line">
          {proposed || <span className="italic text-zen-text-gray">(empty)</span>}
        </div>
      </div>
    </div>
  );
}

function BulkRejectModal({
  count,
  busy,
  onCancel,
  onSubmit,
}: {
  count: number;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (reason: string) => void;
}) {
  const [reason, setReason] = useState('');
  const canSubmit = reason.trim().length > 0 && !busy;
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="bulk-reject-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-zen-dark-green/60 p-4"
    >
      <div className="w-full max-w-md rounded-lg bg-white border border-zen-separator shadow-lg">
        <div className="flex items-start justify-between gap-3 p-4 border-b border-zen-separator">
          <h2 id="bulk-reject-title" className="text-base font-semibold text-zen-dark-green">
            Reject {count} suggestion{count > 1 ? 's' : ''}
          </h2>
          <button
            type="button"
            onClick={onCancel}
            aria-label="close"
            className="text-zen-text-gray hover:text-zen-dark-green"
          >
            <X size={16} />
          </button>
        </div>
        <div className="p-4 space-y-3">
          <p className="text-sm text-zen-dark-teal">
            The same reason will be recorded on every selected suggestion.
            Suggestions that aren't currently <code>pending</code> are skipped.
          </p>
          <label className="block text-sm">
            <span className="text-zen-dark-green">
              Reason <span className="text-zen-orange">(required)</span>
            </span>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              autoFocus
              placeholder="Why are these suggestions being rejected? Recorded in the audit trail."
              className="mt-1 w-full rounded border border-zen-separator bg-white px-2 py-1.5 text-sm text-zen-dark-green focus:outline-none focus:ring-1 focus:ring-zen-teal"
            />
          </label>
        </div>
        <div className="flex items-center justify-end gap-2 p-3 border-t border-zen-separator bg-zen-ice/50">
          <button
            type="button"
            onClick={onCancel}
            className="text-xs px-3 py-1.5 rounded border border-zen-separator text-zen-dark-green hover:bg-zen-light-green/40"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onSubmit(reason.trim())}
            disabled={!canSubmit}
            className="text-xs px-3 py-1.5 rounded bg-zen-orange text-white hover:opacity-90 disabled:opacity-50 inline-flex items-center gap-1"
          >
            {busy && <Loader2 size={10} className="animate-spin" />}
            Reject {count}
          </button>
        </div>
      </div>
    </div>
  );
}
