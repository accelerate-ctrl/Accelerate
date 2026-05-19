// Phase 5 — QA health tile rolled up from /api/qa/*.
//
// Surfaces three signals in one card so engineers + pillar leads can
// see at a glance whether anything needs attention:
//   - Per-user daily budget (IMP-9)
//   - Source-health flagged count (IMP-13)
//   - Retrieval telemetry — structured-hit rate + zero-hit query count (IMP-8)

import { useQuery } from '@tanstack/react-query';
import { Activity, AlertCircle, DollarSign, Radio } from 'lucide-react';
import { apiGet } from '@/lib/api';

type BudgetTile = {
  user_email: string;
  spend_usd: number;
  budget_usd: number;
  fraction: number;
  should_downgrade: boolean;
  admin_override: boolean;
  headroom_usd: number;
};

type SourceHealthTile = {
  n_sources_seen: number;
  n_flagged: number;
  by_flag: Record<string, number>;
};

type RetrievalTile = {
  events: number;
  hits_by_signal: Record<string, number>;
  structured_filter_rate: number;
  zero_hit_queries: string[];
  avg_top_score: number;
};

export default function QaHealthTile() {
  const { data: budget } = useQuery<BudgetTile>({
    queryKey: ['qa-budget'],
    queryFn: () => apiGet<BudgetTile>('/qa/budgets/me'),
    staleTime: 60_000,
  });
  const { data: health } = useQuery<SourceHealthTile>({
    queryKey: ['qa-source-health'],
    queryFn: () => apiGet<SourceHealthTile>('/qa/source-health/latest'),
    staleTime: 60_000,
  });
  const { data: retrieval } = useQuery<RetrievalTile>({
    queryKey: ['qa-retrieval'],
    queryFn: () => apiGet<RetrievalTile>('/qa/retrieval/summary'),
    staleTime: 60_000,
  });

  const budgetPct = budget ? Math.round((budget.fraction || 0) * 100) : 0;
  const budgetTone =
    budgetPct >= 100
      ? 'text-zen-orange'
      : budgetPct >= 80
        ? 'text-zen-orange/80'
        : 'text-zen-dark-green';

  return (
    <div
      data-testid="qa-health-tile"
      className="bg-white rounded-lg border border-zen-separator p-3"
    >
      <h2 className="text-xs font-semibold uppercase tracking-wider text-zen-dark-green flex items-center gap-1.5 mb-2">
        <Activity size={13} /> QA & Audit
      </h2>
      <div className="grid grid-cols-3 gap-2 text-[11px]">
        <div className="flex flex-col">
          <div className="flex items-center gap-1 text-zen-muted-text">
            <DollarSign size={11} /> Your budget
          </div>
          <div className={`mt-0.5 font-mono ${budgetTone}`}>
            ${(budget?.spend_usd ?? 0).toFixed(2)} / ${(budget?.budget_usd ?? 0).toFixed(2)}
          </div>
          <div className="text-[10px] text-zen-muted-text">
            {budget?.should_downgrade
              ? 'Pro → Flash (cap hit)'
              : budget?.admin_override
                ? 'admin override'
                : `${budgetPct}% used`}
          </div>
        </div>
        <div className="flex flex-col">
          <div className="flex items-center gap-1 text-zen-muted-text">
            <AlertCircle size={11} /> Source flags
          </div>
          <div
            className={`mt-0.5 font-mono ${
              (health?.n_flagged ?? 0) > 0
                ? 'text-zen-orange'
                : 'text-zen-dark-green'
            }`}
          >
            {health?.n_flagged ?? 0} / {health?.n_sources_seen ?? 0}
          </div>
          <div className="text-[10px] text-zen-muted-text truncate">
            {Object.entries(health?.by_flag ?? {})
              .map(([k, v]) => `${k}:${v}`)
              .join(' · ') || 'all healthy'}
          </div>
        </div>
        <div className="flex flex-col">
          <div className="flex items-center gap-1 text-zen-muted-text">
            <Radio size={11} /> Retrieval
          </div>
          <div className="mt-0.5 font-mono text-zen-dark-green">
            {retrieval ? `${Math.round((retrieval.structured_filter_rate || 0) * 100)}%` : '—'}
          </div>
          <div className="text-[10px] text-zen-muted-text truncate">
            {retrieval
              ? `${retrieval.events} events · ${retrieval.zero_hit_queries.length} zero-hit`
              : 'no events yet'}
          </div>
        </div>
      </div>
    </div>
  );
}
