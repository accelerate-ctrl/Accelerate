import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, ExternalLink, RefreshCw, Rss } from 'lucide-react';
import { Link } from 'react-router-dom';
import { apiGet, apiPost, type NewsIngestRun, type NewsItem } from '@/lib/api';

export default function NewsWatch() {
  const qc = useQueryClient();

  const { data: items, isLoading } = useQuery<NewsItem[]>({
    queryKey: ['news'],
    queryFn: () => apiGet<NewsItem[]>('/news?limit=200'),
  });

  const refresh = useMutation({
    mutationFn: () => apiPost<NewsIngestRun>('/news/refresh'),
    onSettled: () => qc.invalidateQueries(),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zen-dark-green">News Watch</h1>
          <p className="text-sm text-zen-dark-teal/80">
            Canonical-source news mapped to subcaps. Local seed in dev; RSS swap-in
            when <span className="font-mono">NEWS_FEEDS</span> + live mode are configured.
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
            Loaded <strong>{refresh.data.news_loaded}</strong> news +{' '}
            <strong>{refresh.data.trends_loaded}</strong> trends from{' '}
            <span className="font-mono">{refresh.data.sources.join(', ') || 'none'}</span>
            {refresh.data.schema_issues.length > 0 && (
              <div className="text-zen-orange mt-1">{refresh.data.schema_issues.join('; ')}</div>
            )}
          </div>
        </div>
      )}

      {isLoading && <div className="text-xs text-zen-dark-teal/60">Loading…</div>}

      {items && items.length === 0 && (
        <div className="bg-white rounded-lg border border-zen-light-green/40 p-6 text-center text-sm text-zen-dark-teal/70">
          No news yet. Click <strong>Refresh</strong> to scan seed feeds.
        </div>
      )}

      <ul className="space-y-2">
        {items?.map((n) => (
          <li key={n.id} className="bg-white rounded-lg border border-zen-light-green/40 p-3">
            <div className="flex items-center gap-2 text-xs text-zen-dark-teal/70">
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
            <h3 className="text-sm font-semibold text-zen-dark-green mt-1">{n.title}</h3>
            <p className="text-xs text-zen-dark-teal mt-1 line-clamp-3">{n.text}</p>
            <div className="flex flex-wrap gap-1 mt-2">
              {(n.sub_cap_hits || []).map((h) => (
                <Link
                  key={h}
                  to={`/subcap?id=${encodeURIComponent(h)}`}
                  className="font-mono text-[10px] bg-zen-light-green/50 text-zen-dark-teal px-1 py-0.5 rounded hover:text-zen-dark-green"
                >
                  {h}
                </Link>
              ))}
              {(n.subverticals || []).map((sv) => (
                <span key={sv} className="text-[10px] bg-zen-light-orange/60 text-zen-dark-green px-1 py-0.5 rounded">
                  {sv}
                </span>
              ))}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
