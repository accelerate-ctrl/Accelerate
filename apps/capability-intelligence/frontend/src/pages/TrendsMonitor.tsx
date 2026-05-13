import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ExternalLink, Layers, RefreshCw, TrendingUp } from 'lucide-react';
import { Link } from 'react-router-dom';
import { apiGet, apiPost } from '@/lib/api';

type WeekPoint = { week: string; count: number };
type SourceCount = { source: string; count: number };
type TrendCluster = {
  cluster_id: string;
  label: string;
  summary: string;
  count: number;
  member_ids: string[];
  top_sources: SourceCount[];
  time_series: WeekPoint[];
  impact_class_mix?: Record<string, number>;
  first_seen?: string | null;
  last_seen?: string | null;
};

const IMPACT_DOT: Record<string, string> = {
  catalogue_extension: 'bg-zen-orange',
  reinforcement: 'bg-zen-light-teal',
  benchmark_source: 'bg-zen-blue',
  no_impact: 'bg-zen-muted-text',
};

function Sparkline({ points }: { points: WeekPoint[] }) {
  if (!points || points.length === 0) return null;
  const max = Math.max(...points.map((p) => p.count), 1);
  const w = 120;
  const h = 28;
  const step = points.length > 1 ? w / (points.length - 1) : w;
  const path = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${i * step},${h - (p.count / max) * h}`)
    .join(' ');
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="text-zen-teal">
      <path d={path} fill="none" stroke="currentColor" strokeWidth={1.5} />
      {points.map((p, i) => (
        <circle
          key={i}
          cx={i * step}
          cy={h - (p.count / max) * h}
          r={2}
          fill="currentColor"
        />
      ))}
    </svg>
  );
}

export default function TrendsMonitor() {
  const qc = useQueryClient();
  const { data: clusters, isLoading } = useQuery<TrendCluster[]>({
    queryKey: ['trends'],
    queryFn: () => apiGet<TrendCluster[]>('/news/trends?limit=50'),
  });

  const recompute = useMutation({
    mutationFn: () => apiPost<{ clusters_written: number; items_considered: number }>(
      '/news/trends/recompute',
      {},
    ),
    onSettled: () => qc.invalidateQueries({ queryKey: ['trends'] }),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-semibold text-zen-dark-green">Trends Monitor</h1>
          <p className="text-sm text-zen-dark-teal/80 max-w-3xl">
            Recent news clustered into trend groups (K-Means on 256-d hash embeddings), labelled
            and summarised by Gemini Flash. Each card carries the cluster's impact-class mix so
            you can see at a glance which trends are pushing catalogue extensions vs reinforcing
            existing capabilities.
          </p>
        </div>
        <button
          onClick={() => recompute.mutate()}
          disabled={recompute.isPending}
          className="bg-zen-teal hover:bg-zen-dark-teal text-white text-xs font-medium px-3 py-1.5 rounded transition-colors disabled:opacity-50"
        >
          <RefreshCw size={12} className={`inline mr-1 ${recompute.isPending ? 'animate-spin' : ''}`} />
          {recompute.isPending ? 'Recomputing…' : 'Recompute trends'}
        </button>
      </div>

      {recompute.data && (
        <div className="bg-white border border-zen-separator rounded-lg p-3 text-xs text-zen-text-gray">
          Recomputed: <strong>{recompute.data.clusters_written}</strong> clusters from{' '}
          <strong>{recompute.data.items_considered}</strong> recent news items.
        </div>
      )}

      {isLoading && <div className="text-xs text-zen-muted-text">Loading…</div>}

      {clusters && clusters.length === 0 && (
        <div className="bg-white rounded-lg border border-zen-separator p-6 text-center text-sm text-zen-text-gray">
          No trend clusters yet. Pull news in{' '}
          <Link to="/news" className="underline text-zen-teal">News Watch</Link>, then click{' '}
          <strong>Recompute trends</strong>.
        </div>
      )}

      <ul className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {(clusters || []).map((c) => (
          <li
            key={c.cluster_id}
            className="bg-white rounded-lg border border-zen-separator p-3 flex flex-col"
          >
            <div className="flex items-baseline gap-2">
              <TrendingUp size={14} className="text-zen-teal mt-1" />
              <div className="flex-1">
                <h3 className="text-sm font-semibold text-zen-dark-green">{c.label}</h3>
                <div className="text-[10px] uppercase tracking-wider text-zen-muted-text flex items-center gap-1 mt-0.5">
                  <Layers size={9} /> {c.count} item{c.count === 1 ? '' : 's'}
                  {c.first_seen && c.last_seen && (
                    <>
                      <span>·</span>
                      <span>
                        {new Date(c.first_seen).toLocaleDateString()} →{' '}
                        {new Date(c.last_seen).toLocaleDateString()}
                      </span>
                    </>
                  )}
                </div>
              </div>
              <Sparkline points={c.time_series || []} />
            </div>

            {c.summary && (
              <p className="text-xs text-zen-dark-green mt-2 italic">
                <span className="text-zen-teal not-italic font-semibold mr-1">↳ Implication:</span>
                {c.summary}
              </p>
            )}

            {/* Impact-class mix */}
            {c.impact_class_mix && Object.keys(c.impact_class_mix).length > 0 && (
              <div className="flex items-center gap-2 mt-2 text-[10px]">
                <span className="text-zen-muted-text">Impact mix:</span>
                {Object.entries(c.impact_class_mix).map(([cls, n]) => (
                  <span key={cls} className="inline-flex items-center gap-1 text-zen-text-gray">
                    <span
                      className={`w-2 h-2 rounded-full ${IMPACT_DOT[cls] || 'bg-zen-muted-text'}`}
                      aria-hidden
                    />
                    {cls.replace(/_/g, ' ')} ×{n}
                  </span>
                ))}
              </div>
            )}

            {/* Top sources */}
            {c.top_sources && c.top_sources.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {c.top_sources.map((s) => (
                  <span
                    key={s.source}
                    className="text-[10px] font-mono bg-zen-ice text-zen-text-gray rounded px-1.5 py-0.5"
                  >
                    {s.source} ×{s.count}
                  </span>
                ))}
              </div>
            )}

            <div className="mt-auto pt-2 flex items-center justify-between">
              <Link
                to={`/news?cluster=${encodeURIComponent(c.cluster_id)}`}
                className="text-[10px] text-zen-teal hover:text-zen-dark-teal underline inline-flex items-center gap-0.5"
              >
                Inspect cluster <ExternalLink size={9} />
              </Link>
              <span className="text-[10px] text-zen-muted-text font-mono">
                {c.cluster_id.slice(-8)}
              </span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
