import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import {
  CheckCircle2,
  ExternalLink,
  Lightbulb,
  RefreshCw,
  Rss,
  Sparkles,
  Wand2,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { apiGet, apiPost, type NewsIngestRun, type NewsItem } from '@/lib/api';

type Impact = {
  summary?: string;
  impact_class?:
    | 'catalogue_extension'
    | 'reinforcement'
    | 'benchmark_source'
    | 'no_impact';
  affects_subcaps?: string[];
  suggests_new_subcap?: {
    name: string;
    rationale: string;
    candidate_l1?: string;
  } | null;
  confidence?: number;
  synthesised_at?: string;
};

const IMPACT_BAND: Record<string, { bg: string; accent: string; label: string }> = {
  catalogue_extension: {
    bg: 'bg-zen-light-orange/40',
    accent: 'text-zen-orange',
    label: 'Catalogue extension',
  },
  reinforcement: {
    bg: 'bg-zen-light-green/60',
    accent: 'text-zen-dark-teal',
    label: 'Reinforces existing',
  },
  benchmark_source: {
    bg: 'bg-zen-light-blue/40',
    accent: 'text-zen-blue',
    label: 'New benchmark source',
  },
  no_impact: {
    bg: 'bg-zen-ice',
    accent: 'text-zen-muted-text',
    label: 'No catalogue impact',
  },
};

export default function NewsWatch() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<string>('');

  const { data: items, isLoading } = useQuery<(NewsItem & { impact?: Impact })[]>({
    queryKey: ['news'],
    queryFn: () => apiGet<(NewsItem & { impact?: Impact })[]>('/news?limit=200'),
  });

  const refresh = useMutation({
    mutationFn: () => apiPost<NewsIngestRun>('/news/refresh'),
    onSettled: () => qc.invalidateQueries(),
  });

  const synth = useMutation({
    mutationFn: () => apiPost<{ synthesised: number; scanned: number; errors: number }>(
      '/news/impact-synthesise', {},
    ),
    onSettled: () => qc.invalidateQueries({ queryKey: ['news'] }),
  });

  const propose = useMutation({
    mutationFn: (newsId: string) => apiPost(`/news/${encodeURIComponent(newsId)}/propose-change`, {}),
    onSettled: () => qc.invalidateQueries(),
  });

  const filtered = (items || []).filter((n) => {
    if (!filter) return true;
    return (n.impact?.impact_class || 'no_impact') === filter;
  });

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-semibold text-zen-dark-green">News Watch</h1>
          <p className="text-sm text-zen-dark-teal/80 max-w-3xl">
            Canonical-source news mapped to subcaps, with per-item impact synthesis (Gemini Flash)
            classifying whether the article would <b>extend</b>, <b>reinforce</b>, or surface a
            new <b>benchmark source</b> for the catalogue. Click <b>Propose change</b> on any
            insightful card to send it to the AI Suggestions board.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => synth.mutate()}
            disabled={synth.isPending}
            className="bg-zen-dark-teal hover:bg-zen-dark-green text-white text-xs font-medium px-3 py-1.5 rounded transition-colors disabled:opacity-50"
            title="Run Gemini Flash impact classification on items without an impact block"
          >
            <Wand2 size={12} className={`inline mr-1 ${synth.isPending ? 'animate-pulse' : ''}`} />
            {synth.isPending ? 'Synthesising…' : 'Synthesise impact'}
          </button>
          <button
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending}
            className="bg-zen-teal hover:bg-zen-dark-teal text-white text-xs font-medium px-3 py-1.5 rounded transition-colors disabled:opacity-50"
          >
            <RefreshCw size={12} className={`inline mr-1 ${refresh.isPending ? 'animate-spin' : ''}`} />
            Refresh feeds
          </button>
        </div>
      </div>

      {refresh.data && (
        <div className="bg-white border border-zen-separator rounded-lg p-3 text-xs text-zen-text-gray flex items-start gap-2">
          <CheckCircle2 size={14} className="text-zen-teal mt-0.5" />
          <div>
            Loaded <strong>{refresh.data.news_loaded}</strong> news +{' '}
            <strong>{refresh.data.trends_loaded}</strong> trends from{' '}
            <span className="font-mono">{refresh.data.sources.join(', ') || 'none'}</span>
            {refresh.data.schema_issues.length > 0 && (
              <div className="text-zen-orange mt-1">{refresh.data.schema_issues.join('; ')}</div>
            )}
          </div>
        </div>
      )}

      {synth.data && (
        <div className="bg-white border border-zen-separator rounded-lg p-3 text-xs text-zen-text-gray flex items-center gap-2">
          <Sparkles size={14} className="text-zen-teal" />
          Impact synthesis: <strong>{synth.data.synthesised}</strong> classified ·{' '}
          <strong>{synth.data.scanned}</strong> scanned ·{' '}
          <strong>{synth.data.errors}</strong> errors
        </div>
      )}

      {/* Impact-class filter pills */}
      <div className="flex flex-wrap items-center gap-1">
        <button
          onClick={() => setFilter('')}
          className={`text-[11px] px-2 py-1 rounded ${
            !filter
              ? 'bg-zen-dark-green text-white'
              : 'bg-zen-ice text-zen-text-gray hover:bg-zen-ice/80'
          }`}
        >
          All
        </button>
        {Object.entries(IMPACT_BAND).map(([k, b]) => (
          <button
            key={k}
            onClick={() => setFilter(k)}
            className={`text-[11px] px-2 py-1 rounded ${
              filter === k
                ? 'bg-zen-dark-green text-white'
                : `${b.bg} ${b.accent} hover:opacity-80`
            }`}
          >
            {b.label}
          </button>
        ))}
      </div>

      {isLoading && <div className="text-xs text-zen-muted-text">Loading…</div>}

      {items && items.length === 0 && (
        <div className="bg-white rounded-lg border border-zen-separator p-6 text-center text-sm text-zen-text-gray">
          No news yet. Click <strong>Refresh feeds</strong> to pull from configured RSS sources.
        </div>
      )}

      <ul className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {filtered.map((n) => {
          const impact = n.impact || {};
          const band = IMPACT_BAND[impact.impact_class || 'no_impact'];
          return (
            <li
              key={n.id}
              className="bg-white rounded-lg border border-zen-separator overflow-hidden flex flex-col"
            >
              <div className={`${band.bg} px-3 py-2 flex items-center gap-2`}>
                <span className={`text-[10px] uppercase tracking-wider font-semibold ${band.accent}`}>
                  {band.label}
                </span>
                {typeof impact.confidence === 'number' && impact.confidence > 0 && (
                  <span className="text-[10px] text-zen-muted-text ml-auto">
                    conf {impact.confidence.toFixed(2)}
                  </span>
                )}
              </div>
              <div className="p-3 flex-1 flex flex-col">
                <div className="flex items-center gap-2 text-xs text-zen-text-gray">
                  <Rss size={11} className="text-zen-teal" />
                  <span className="font-mono">{n.source}</span>
                  <span>·</span>
                  <span>{new Date(n.published_at).toLocaleDateString()}</span>
                  {n.url && (
                    <a
                      href={n.url}
                      target="_blank"
                      rel="noreferrer"
                      className="ml-auto text-zen-teal hover:text-zen-dark-teal inline-flex items-center gap-0.5"
                    >
                      source <ExternalLink size={10} />
                    </a>
                  )}
                </div>
                <h3 className="text-sm font-semibold text-zen-dark-green mt-1">
                  {n.url ? (
                    <a href={n.url} target="_blank" rel="noreferrer" className="hover:underline">
                      {n.title}
                    </a>
                  ) : (
                    n.title
                  )}
                </h3>
                {impact.summary ? (
                  <p className="text-xs text-zen-dark-green mt-1.5 italic">
                    <span className="text-zen-teal not-italic font-semibold mr-1">↳ Insight:</span>
                    {impact.summary}
                  </p>
                ) : (
                  <p className="text-xs text-zen-text-gray mt-1 line-clamp-3">{n.text}</p>
                )}

                {/* Affected subcaps: prefer LLM-inferred `affects_subcaps`,
                    fall back to ingest-time fuzzy `sub_cap_hits`. */}
                <div className="flex flex-wrap gap-1 mt-2">
                  {((impact.affects_subcaps && impact.affects_subcaps.length > 0
                    ? impact.affects_subcaps
                    : (n.sub_cap_hits || [])) as string[]).map((h) => (
                    <Link
                      key={h}
                      to={`/subcap?id=${encodeURIComponent(h)}`}
                      className="font-mono text-[10px] bg-zen-light-green/60 text-zen-dark-teal px-1 py-0.5 rounded hover:text-zen-dark-green"
                    >
                      {h}
                    </Link>
                  ))}
                  {(n.subverticals || []).slice(0, 3).map((sv) => (
                    <span
                      key={sv}
                      className="text-[10px] bg-zen-purple-grey/40 text-zen-text-gray px-1 py-0.5 rounded"
                    >
                      {sv}
                    </span>
                  ))}
                </div>

                {/* Suggested new subcap */}
                {impact.suggests_new_subcap && (
                  <div className="mt-2 border-l-2 border-zen-teal bg-zen-ice/60 pl-2 py-1 rounded-r">
                    <div className="text-[10px] uppercase tracking-wider font-semibold text-zen-teal flex items-center gap-1">
                      <Lightbulb size={10} /> Proposed new sub-capability
                    </div>
                    <div className="text-xs text-zen-dark-green font-medium">
                      {impact.suggests_new_subcap.name}
                    </div>
                    <div className="text-[11px] text-zen-text-gray">
                      {impact.suggests_new_subcap.rationale}
                    </div>
                    {impact.suggests_new_subcap.candidate_l1 && (
                      <div className="text-[10px] text-zen-muted-text mt-0.5">
                        Candidate L1: {impact.suggests_new_subcap.candidate_l1}
                      </div>
                    )}
                  </div>
                )}

                {/* Footer actions */}
                <div className="mt-auto pt-2 flex items-center justify-between">
                  <div className="text-[10px] text-zen-muted-text">
                    {impact.synthesised_at ? (
                      <>synth {new Date(impact.synthesised_at).toLocaleDateString()}</>
                    ) : (
                      <em>impact not synthesised yet</em>
                    )}
                  </div>
                  {(impact.impact_class === 'catalogue_extension' ||
                    impact.impact_class === 'benchmark_source') && (
                    <button
                      type="button"
                      disabled={propose.isPending}
                      onClick={() => propose.mutate(n.id)}
                      className="text-[10px] bg-zen-teal hover:bg-zen-dark-teal text-white px-2 py-1 rounded disabled:opacity-50"
                    >
                      Propose change
                    </button>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
