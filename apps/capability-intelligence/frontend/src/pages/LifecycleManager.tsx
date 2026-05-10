import { useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowRight, CheckCircle2, RefreshCw, TrendingUp, Activity, Minus, AlertTriangle, ZapOff } from 'lucide-react';
import { Link } from 'react-router-dom';
import {
  apiGet,
  apiPost,
  type LifecycleRunSummary,
  type LifecycleScore,
  type LifecycleState,
  type LifecycleTransition,
} from '@/lib/api';

const STATE_ORDER: LifecycleState[] = ['EMERGING', 'RISING', 'STABLE', 'DECLINING', 'FADING', 'DEAD'];

const STATE_HEADER: Record<LifecycleState, { label: string; tone: string; Icon: typeof TrendingUp }> = {
  EMERGING: { label: 'Emerging', tone: 'bg-zen-light-orange text-zen-dark-green', Icon: TrendingUp },
  RISING: { label: 'Rising', tone: 'bg-zen-teal text-white', Icon: TrendingUp },
  STABLE: { label: 'Stable', tone: 'bg-zen-light-green/70 text-zen-dark-green', Icon: Activity },
  DECLINING: { label: 'Declining', tone: 'bg-zen-light-orange/70 text-zen-dark-green', Icon: Minus },
  FADING: { label: 'Fading', tone: 'bg-zen-orange/40 text-zen-dark-green', Icon: AlertTriangle },
  DEAD: { label: 'Dead', tone: 'bg-zen-dark-teal/40 text-zen-white-green', Icon: ZapOff },
};

export default function LifecycleManager() {
  const qc = useQueryClient();

  const { data: scores, isLoading } = useQuery<LifecycleScore[]>({
    queryKey: ['lifecycle-scores'],
    queryFn: () => apiGet<LifecycleScore[]>('/lifecycle?limit=2000'),
  });

  const { data: transitions } = useQuery<LifecycleTransition[]>({
    queryKey: ['lifecycle-transitions'],
    queryFn: () => apiGet<LifecycleTransition[]>('/lifecycle/transitions?limit=20'),
  });

  const recompute = useMutation({
    mutationFn: () => apiPost<LifecycleRunSummary>('/lifecycle/recompute'),
    onSettled: () => qc.invalidateQueries(),
  });

  const byState = useMemo(() => {
    const map: Record<LifecycleState, LifecycleScore[]> = {
      EMERGING: [], RISING: [], STABLE: [], DECLINING: [], FADING: [], DEAD: [],
    };
    for (const s of scores || []) {
      map[s.state]?.push(s);
    }
    return map;
  }, [scores]);

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zen-dark-green">Lifecycle Manager</h1>
          <p className="text-sm text-zen-dark-teal/80">
            6-state weighted scoring across every subcap. Inputs: SOW recency (Batch 3) + story
            velocity + news / trends cadence (Batch 4) + benchmark coverage (Batch 5).
          </p>
        </div>
        <button
          onClick={() => recompute.mutate()}
          disabled={recompute.isPending}
          className="bg-zen-teal hover:bg-zen-dark-teal text-white text-xs font-medium px-3 py-1.5 rounded transition-colors disabled:opacity-50"
        >
          <RefreshCw size={12} className={`inline mr-1 ${recompute.isPending ? 'animate-spin' : ''}`} /> Recompute
        </button>
      </div>

      {recompute.data && (
        <div className="bg-white border border-zen-light-green/40 rounded-lg p-3 text-xs text-zen-dark-teal flex items-start gap-2">
          <CheckCircle2 size={14} className="text-zen-teal mt-0.5" />
          <div>
            Scored <strong>{recompute.data.subcaps_scored}</strong> subcaps. Transitions:{' '}
            <strong>{recompute.data.transitions}</strong>. Inputs:{' '}
            {Object.entries(recompute.data.inputs_seen)
              .map(([k, v]) => `${k}=${v}`)
              .join(', ')}
          </div>
        </div>
      )}

      {isLoading && <div className="text-xs text-zen-dark-teal/60">Loading…</div>}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6 gap-3">
        {STATE_ORDER.map((state) => {
          const meta = STATE_HEADER[state];
          const Icon = meta.Icon;
          const items = byState[state];
          return (
            <div key={state} className="bg-white rounded-lg border border-zen-light-green/40 flex flex-col">
              <div className={`px-3 py-2 rounded-t-lg flex items-center gap-2 ${meta.tone}`}>
                <Icon size={14} />
                <span className="text-xs uppercase font-semibold tracking-wider">{meta.label}</span>
                <span className="ml-auto text-[10px] opacity-80">{items.length}</span>
              </div>
              <ul className="divide-y divide-zen-light-green/30 max-h-[640px] overflow-auto p-1">
                {items.length === 0 && (
                  <li className="text-[10px] text-zen-dark-teal/50 italic px-2 py-1">empty</li>
                )}
                {items.slice(0, 80).map((s) => (
                  <li key={s.sub_cap_id} className="px-2 py-1.5 hover:bg-zen-white-green/50 rounded">
                    <div className="flex items-center gap-2">
                      <Link
                        to={`/subcap?id=${encodeURIComponent(s.sub_cap_id)}`}
                        className="font-mono text-[10px] text-zen-teal hover:text-zen-dark-teal"
                      >
                        {s.sub_cap_id}
                      </Link>
                      <span className="text-[10px] text-zen-dark-teal/70 ml-auto">
                        {s.score.toFixed(0)}
                      </span>
                    </div>
                    <div className="text-xs text-zen-dark-green truncate">{s.sub_cap_name}</div>
                    <div className="text-[9px] text-zen-dark-teal/60 mt-0.5 flex flex-wrap gap-x-1.5">
                      {s.signals.sow_active > 0 && <span>sow:{s.signals.sow_active}A</span>}
                      {s.signals.sow_prospect > 0 && <span>{s.signals.sow_prospect}P</span>}
                      {s.signals.news_last_90d > 0 && <span>news:{s.signals.news_last_90d}</span>}
                      {(s.signals.benchmark_full + s.signals.benchmark_indicative) > 0 && (
                        <span>bench:{s.signals.benchmark_full + s.signals.benchmark_indicative}</span>
                      )}
                      {s.signals.canonical_stories > 0 && <span>stories:{s.signals.canonical_stories}</span>}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>

      {transitions && transitions.length > 0 && (
        <div className="bg-white rounded-lg border border-zen-light-green/40 p-3">
          <h2 className="text-xs uppercase font-semibold tracking-wider text-zen-dark-green mb-2">
            Recent transitions
          </h2>
          <ul className="space-y-1 text-xs">
            {transitions.map((t) => (
              <li key={t.id} className="flex items-center gap-2 text-zen-dark-teal">
                <Link
                  to={`/subcap?id=${encodeURIComponent(t.sub_cap_id)}`}
                  className="font-mono text-[10px] text-zen-teal hover:text-zen-dark-teal"
                >
                  {t.sub_cap_id}
                </Link>
                <span className="text-[10px] uppercase rounded px-1 bg-zen-light-green/40 text-zen-dark-teal">
                  {t.from_state}
                </span>
                <ArrowRight size={10} className="text-zen-dark-teal/60" />
                <span
                  className={`text-[10px] uppercase rounded px-1 ${STATE_HEADER[t.to_state]?.tone || ''}`}
                >
                  {t.to_state}
                </span>
                <span className="ml-auto text-[10px] text-zen-dark-teal/60">
                  {new Date(t.transitioned_at).toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
