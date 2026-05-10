import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, RefreshCw, Sparkles, Database, Brain, ExternalLink } from 'lucide-react';
import { Link } from 'react-router-dom';
import {
  apiGet,
  apiPost,
  type BenchmarkCohort,
  type BenchmarkDistribution,
  type BenchmarkMetric,
  type BenchmarkObservation,
  type BenchmarkSource,
  type BenchmarkVerdict,
  type BenchmarksRefreshSummary,
} from '@/lib/api';

const VERDICT_BADGE: Record<BenchmarkVerdict, string> = {
  BENCHMARK: 'bg-zen-teal text-white',
  INDICATIVE: 'bg-zen-light-orange text-zen-dark-green',
  EXPLORATORY: 'bg-zen-orange text-white',
};

export default function BenchmarksStudio() {
  const qc = useQueryClient();
  const [metricFilter, setMetricFilter] = useState<string>('');
  const [cohortFilter, setCohortFilter] = useState<string>('');
  const [openDist, setOpenDist] = useState<string | null>(null);

  const { data: metrics } = useQuery<BenchmarkMetric[]>({
    queryKey: ['bm-metrics'],
    queryFn: () => apiGet<BenchmarkMetric[]>('/benchmarks/metrics'),
  });
  const { data: cohorts } = useQuery<BenchmarkCohort[]>({
    queryKey: ['bm-cohorts'],
    queryFn: () => apiGet<BenchmarkCohort[]>('/benchmarks/cohorts'),
  });
  const { data: dists, isLoading } = useQuery<BenchmarkDistribution[]>({
    queryKey: ['bm-dists', metricFilter, cohortFilter],
    queryFn: () => {
      const qs = new URLSearchParams();
      if (metricFilter) qs.set('metric_id', metricFilter);
      if (cohortFilter) qs.set('cohort_id', cohortFilter);
      const q = qs.toString();
      return apiGet<BenchmarkDistribution[]>(`/benchmarks${q ? '?' + q : ''}`);
    },
  });
  const { data: sources } = useQuery<BenchmarkSource[]>({
    queryKey: ['bm-sources'],
    queryFn: () => apiGet<BenchmarkSource[]>('/benchmarks/sources'),
  });

  const refresh = useMutation({
    mutationFn: () => apiPost<BenchmarksRefreshSummary>('/benchmarks/refresh?extrapolate=true'),
    onSettled: () => qc.invalidateQueries(),
  });

  const metricById = useMemo(() => Object.fromEntries((metrics || []).map((m) => [m.metric_id, m])), [metrics]);
  const cohortById = useMemo(() => Object.fromEntries((cohorts || []).map((c) => [c.cohort_id, c])), [cohorts]);

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zen-dark-green">Benchmarks Studio</h1>
          <p className="text-sm text-zen-dark-teal/80">
            Per-cohort distributions for FS metrics. Sources: SEC EDGAR filings, FDIC Call Report,
            analyst extracts (Gartner / Forrester / Celent), technographic providers (BuiltWith,
            Wappalyzer). Sparse cohorts get an AI-extrapolated estimate (verdict EXPLORATORY).
          </p>
        </div>
        <button
          onClick={() => refresh.mutate()}
          disabled={refresh.isPending}
          className="bg-zen-teal hover:bg-zen-dark-teal text-white text-xs font-medium px-3 py-1.5 rounded transition-colors disabled:opacity-50"
        >
          <RefreshCw size={12} className={`inline mr-1 ${refresh.isPending ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      {refresh.data && (
        <div className="bg-white border border-zen-light-green/40 rounded-lg p-3 text-xs text-zen-dark-teal flex items-start gap-2">
          <CheckCircle2 size={14} className="text-zen-teal mt-0.5" />
          <div>
            Loaded <strong>{refresh.data.observations_total}</strong> observations
            ({refresh.data.filings_loaded} filings, {refresh.data.analyst_observations} analyst,
            {' '}{refresh.data.technographic_companies} technographic) →{' '}
            <strong>{refresh.data.distributions_total}</strong> distributions across{' '}
            <strong>{refresh.data.cohorts_loaded}</strong> cohorts. AI-extrapolated:{' '}
            <strong>{refresh.data.extrapolations_total}</strong>.
            {refresh.data.schema_issues.length > 0 && (
              <div className="text-zen-orange mt-1">{refresh.data.schema_issues.join('; ')}</div>
            )}
          </div>
        </div>
      )}

      <div className="bg-white rounded-lg border border-zen-light-green/40 p-3 grid grid-cols-1 md:grid-cols-2 gap-2">
        <label className="text-xs text-zen-dark-teal/80">
          Metric
          <select
            value={metricFilter}
            onChange={(e) => setMetricFilter(e.target.value)}
            className="block w-full mt-0.5 border border-zen-light-green rounded px-2 py-1 text-xs"
          >
            <option value="">all metrics</option>
            {(metrics || []).map((m) => (
              <option key={m.metric_id} value={m.metric_id}>{m.name} ({m.metric_id})</option>
            ))}
          </select>
        </label>
        <label className="text-xs text-zen-dark-teal/80">
          Cohort
          <select
            value={cohortFilter}
            onChange={(e) => setCohortFilter(e.target.value)}
            className="block w-full mt-0.5 border border-zen-light-green rounded px-2 py-1 text-xs"
          >
            <option value="">all cohorts</option>
            {(cohorts || []).map((c) => (
              <option key={c.cohort_id} value={c.cohort_id}>{c.name}</option>
            ))}
          </select>
        </label>
      </div>

      {isLoading && <div className="text-xs text-zen-dark-teal/60">Loading…</div>}

      {dists && dists.length === 0 && (
        <div className="bg-white rounded-lg border border-zen-light-green/40 p-6 text-center text-sm text-zen-dark-teal/70">
          No distributions yet. Click <strong>Refresh</strong> to ingest seed filings + analyst
          reports + technographics, then compute distributions.
        </div>
      )}

      <div className="bg-white rounded-lg border border-zen-light-green/40 divide-y divide-zen-light-green/30">
        {dists?.map((d) => (
          <div key={d.id} className="p-3">
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`text-[10px] uppercase rounded px-1.5 py-0.5 ${VERDICT_BADGE[d.verdict]}`}>
                {d.verdict}
              </span>
              <span className="text-sm font-medium text-zen-dark-green">
                {metricById[d.metric_id]?.name || d.metric_id}
              </span>
              <span className="text-zen-dark-teal/60">·</span>
              <span className="text-xs text-zen-dark-teal/80">{cohortById[d.cohort_id]?.name || d.cohort_id}</span>
              <span className="text-zen-dark-teal/60">·</span>
              <span className="text-xs text-zen-dark-teal/80">{d.period}</span>
              <span className="ml-auto text-xs text-zen-dark-teal/70">N={d.n}</span>
            </div>
            <DistributionBar dist={d} unit={metricById[d.metric_id]?.unit} />
            <div className="text-[10px] text-zen-dark-teal/60 mt-1 flex flex-wrap gap-x-3">
              <span>p25 <strong>{d.p25.toFixed(2)}</strong></span>
              <span>p50 <strong>{d.p50.toFixed(2)}</strong></span>
              <span>p75 <strong>{d.p75.toFixed(2)}</strong></span>
              <span>mean <strong>{d.mean?.toFixed(2)}</strong></span>
              <span>cv <strong>{d.coef_var.toFixed(2)}</strong></span>
              <span className="ml-auto inline-flex items-center gap-1">
                <Database size={10} /> sources: {d.source_kinds.join(', ')}
              </span>
              <button onClick={() => setOpenDist(openDist === d.id ? null : d.id)} className="ml-2 text-zen-teal hover:text-zen-dark-teal underline">
                {openDist === d.id ? 'hide' : 'observations'}
              </button>
            </div>
            {openDist === d.id && <DistributionDetail distId={d.id} />}
          </div>
        ))}
      </div>

      {sources && sources.length > 0 && (
        <div className="bg-white rounded-lg border border-zen-light-green/40 p-3">
          <h2 className="text-xs uppercase font-semibold tracking-wider text-zen-dark-green mb-2">Sources</h2>
          <ul className="grid grid-cols-1 md:grid-cols-2 gap-1 text-xs">
            {sources.map((s) => (
              <li key={s.id} className="flex items-center gap-2 text-zen-dark-teal">
                <span className="text-[10px] uppercase rounded px-1 bg-zen-light-green/50 text-zen-dark-teal">{s.kind}</span>
                <span className="font-mono text-[10px] text-zen-dark-teal/70">[{s.tier}]</span>
                <span>{s.label}</span>
                <span className="text-[10px] text-zen-dark-teal/60 ml-auto">{s.observation_count} obs</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function DistributionBar({ dist, unit }: { dist: BenchmarkDistribution; unit?: string }) {
  const lo = dist.min ?? dist.p25;
  const hi = dist.max ?? dist.p75;
  if (lo === null || hi === null || lo === hi) return null;
  const span = hi - lo;
  const left = ((dist.p25 - lo) / span) * 100;
  const right = ((dist.p75 - lo) / span) * 100;
  const med = ((dist.p50 - lo) / span) * 100;
  return (
    <div className="mt-2 relative h-2 bg-zen-light-green/40 rounded">
      <div
        className="absolute h-2 bg-zen-teal/60 rounded"
        style={{ left: `${left}%`, width: `${Math.max(2, right - left)}%` }}
        title={`${unit ?? ''} p25-p75: ${dist.p25.toFixed(2)} – ${dist.p75.toFixed(2)}`}
      />
      <div
        className="absolute h-2 w-0.5 bg-zen-dark-green"
        style={{ left: `${med}%` }}
        title={`p50: ${dist.p50.toFixed(2)}`}
      />
    </div>
  );
}

function DistributionDetail({ distId }: { distId: string }) {
  const { data } = useQuery<BenchmarkDistribution>({
    queryKey: ['bm-dist', distId],
    queryFn: () => apiGet<BenchmarkDistribution>(`/benchmarks/${encodeURIComponent(distId)}`),
  });
  const { data: obs } = useQuery<BenchmarkObservation[]>({
    queryKey: ['bm-obs', distId, data?.metric_id, data?.cohort_id],
    enabled: !!data,
    queryFn: () =>
      apiGet<BenchmarkObservation[]>(
        `/benchmarks/observations?metric_id=${encodeURIComponent(data!.metric_id)}&cohort_id=${encodeURIComponent(data!.cohort_id)}`,
      ),
  });
  if (!data) return <div className="text-xs text-zen-dark-teal/60 mt-2">Loading…</div>;
  return (
    <ul className="mt-2 space-y-1 text-xs bg-zen-white-green/60 rounded p-2">
      {(obs || []).map((o) => (
        <li key={o.id} className="text-zen-dark-teal flex items-start gap-2">
          {o.is_extrapolated ? (
            <span className="text-[10px] uppercase rounded px-1 bg-zen-orange/40 text-zen-dark-green inline-flex items-center gap-0.5">
              <Sparkles size={9} /> AI
            </span>
          ) : (
            <span className="text-[10px] uppercase rounded px-1 bg-zen-light-green/50 text-zen-dark-teal">
              {o.source_kind}
            </span>
          )}
          <span className="font-medium text-zen-dark-green">{o.company}</span>
          <span>= <strong>{o.value}</strong></span>
          <span className="text-zen-dark-teal/60">[{o.source_label}]</span>
          {o.evidence && <span className="text-[10px] italic text-zen-dark-teal/70">{o.evidence}</span>}
          {o.chain_id && (
            <Link
              to={`/reasoning-chain?id=${encodeURIComponent(o.chain_id)}`}
              className="ml-auto inline-flex items-center gap-0.5 text-zen-teal hover:text-zen-dark-teal"
            >
              <Brain size={9} /> chain
            </Link>
          )}
          {o.source_url && (
            <a href={o.source_url} target="_blank" rel="noreferrer" className="text-zen-teal hover:text-zen-dark-teal">
              <ExternalLink size={9} />
            </a>
          )}
        </li>
      ))}
    </ul>
  );
}
