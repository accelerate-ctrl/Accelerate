import { useQuery } from '@tanstack/react-query';
import { ExternalLink } from 'lucide-react';
import { apiGet, type PlatformCatalog as PC } from '@/lib/api';

export default function PlatformCatalog() {
  const { data, isLoading } = useQuery<PC>({
    queryKey: ['platform-catalog'],
    queryFn: () => apiGet<PC>('/lens/platform-catalog'),
  });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-zen-dark-green">Platform Catalog</h1>
        <p className="text-sm text-zen-dark-teal/80">
          L3 platforms grouped by vendor. Each card shows the number of subcaps that name it.
        </p>
      </div>

      {isLoading && <div className="text-xs text-zen-dark-teal/60">Loading…</div>}

      {data && (
        <>
          <div className="text-sm text-zen-dark-teal">
            Total platforms: <span className="font-mono font-semibold">{data.total_platforms}</span>
          </div>
          <div className="space-y-3">
            {data.vendors.map((v) => (
              <div key={v.vendor} className="bg-white rounded-lg border border-zen-light-green/40 p-3">
                <div className="flex items-center justify-between mb-2">
                  <h2 className="text-sm font-semibold text-zen-dark-green">{v.vendor}</h2>
                  <div className="text-xs text-zen-dark-teal/70">
                    {v.platform_count} platforms · {v.total_subcaps_using} subcap links
                  </div>
                </div>
                <ul className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
                  {v.platforms.map((p) => (
                    <li key={p.l3_id} className="border border-zen-light-green/40 rounded p-2 text-xs">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0 flex-1">
                          <div className="font-mono text-[10px] text-zen-dark-teal/60">{p.l3_id}</div>
                          <div className="text-zen-dark-green font-medium truncate" title={p.name}>{p.name}</div>
                          {p.category && (
                            <div className="text-[10px] text-zen-dark-teal/60">{p.category}</div>
                          )}
                        </div>
                        <span className="bg-zen-light-green/60 text-zen-dark-teal rounded px-1.5 py-0.5 text-[10px] font-mono">
                          ×{p.subcap_count}
                        </span>
                      </div>
                      {p.description && (
                        <div className="text-zen-dark-teal/80 mt-1 line-clamp-3" title={p.description}>
                          {p.description.slice(0, 140)}
                        </div>
                      )}
                      {p.reference_url && (
                        <a
                          href={p.reference_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-[10px] text-zen-teal hover:text-zen-dark-teal mt-1 inline-flex items-center gap-0.5"
                        >
                          docs <ExternalLink size={10} />
                        </a>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
