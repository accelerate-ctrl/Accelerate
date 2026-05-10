import { useQuery } from '@tanstack/react-query';
import { TrendingUp, ExternalLink } from 'lucide-react';
import { Link } from 'react-router-dom';
import { apiGet, type NewsItem } from '@/lib/api';

export default function TrendsMonitor() {
  const { data: items, isLoading } = useQuery<NewsItem[]>({
    queryKey: ['trends'],
    queryFn: () => apiGet<NewsItem[]>('/trends?limit=200'),
  });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-zen-dark-green">Trends Monitor</h1>
        <p className="text-sm text-zen-dark-teal/80">
          Long-running market signals from analysts, research notes, and vendor releases.
          Refresh shares the same ingest run as <Link to="/news" className="underline text-zen-teal hover:text-zen-dark-teal">News Watch</Link>.
        </p>
      </div>

      {isLoading && <div className="text-xs text-zen-dark-teal/60">Loading…</div>}

      {items && items.length === 0 && (
        <div className="bg-white rounded-lg border border-zen-light-green/40 p-6 text-center text-sm text-zen-dark-teal/70">
          No trends yet. Trigger <Link to="/news" className="underline text-zen-teal">News Watch → Refresh</Link> to seed.
        </div>
      )}

      <ul className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {items?.map((t) => (
          <li key={t.id} className="bg-white rounded-lg border border-zen-light-green/40 p-3">
            <div className="flex items-center gap-2 text-xs text-zen-dark-teal/70">
              <TrendingUp size={12} className="text-zen-teal" />
              <span className="font-mono">{t.source}</span>
              <span>·</span>
              <span>{new Date(t.published_at).toLocaleDateString()}</span>
              {t.url && (
                <a
                  href={t.url}
                  target="_blank"
                  rel="noreferrer"
                  className="ml-auto text-zen-teal hover:text-zen-dark-teal inline-flex items-center gap-0.5"
                >
                  read <ExternalLink size={10} />
                </a>
              )}
            </div>
            <h3 className="text-sm font-semibold text-zen-dark-green mt-1">{t.title}</h3>
            <p className="text-xs text-zen-dark-teal mt-1">{t.text}</p>
            <div className="flex flex-wrap gap-1 mt-2">
              {(t.sub_cap_hits || []).map((h) => (
                <Link
                  key={h}
                  to={`/subcap?id=${encodeURIComponent(h)}`}
                  className="font-mono text-[10px] bg-zen-light-green/50 text-zen-dark-teal px-1 py-0.5 rounded hover:text-zen-dark-green"
                >
                  {h}
                </Link>
              ))}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
