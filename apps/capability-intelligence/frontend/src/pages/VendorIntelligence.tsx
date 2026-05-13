import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, RefreshCw, ExternalLink, Building2 } from 'lucide-react';
import { apiGet, apiPost, type VendorEvent, type VendorHeatmap, type VendorProfile } from '@/lib/api';

export default function VendorIntelligence() {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<string | null>(null);

  const { data: vendors } = useQuery<VendorProfile[]>({
    queryKey: ['vendors'],
    queryFn: () => apiGet<VendorProfile[]>('/vendor-intel/vendors'),
  });
  const { data: heatmap } = useQuery<VendorHeatmap>({
    queryKey: ['vendor-heatmap'],
    queryFn: () => apiGet<VendorHeatmap>('/vendor-intel/heatmap'),
  });
  const { data: events } = useQuery<VendorEvent[]>({
    queryKey: ['vendor-events', selected],
    queryFn: () =>
      apiGet<VendorEvent[]>(
        selected ? `/vendor-intel/events?vendor_id=${encodeURIComponent(selected)}` : '/vendor-intel/events',
      ),
  });

  const refresh = useMutation({
    mutationFn: () => apiPost<{ vendors_loaded: number; adoption_rows: number; events_loaded: number }>('/vendor-intel/refresh'),
    onSettled: () => qc.invalidateQueries(),
  });

  const cellByKey = useMemo(() => {
    const map = new Map<string, VendorHeatmap['cells'][number]>();
    for (const c of heatmap?.cells || []) {
      map.set(`${c.vendor_id}__${c.cohort_id}`, c);
    }
    return map;
  }, [heatmap]);

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zen-dark-green">Vendor Intelligence</h1>
          <p className="text-sm text-zen-dark-teal/80">
            Per-vendor adoption % across peer cohorts (Batch 5 technographics) + recent
            news / trend mentions (Batch 4). Click a vendor to filter events.
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
            <strong>{refresh.data.vendors_loaded}</strong> vendors,{' '}
            <strong>{refresh.data.adoption_rows}</strong> adoption rows,{' '}
            <strong>{refresh.data.events_loaded}</strong> news events indexed.
          </div>
        </div>
      )}

      <div className="bg-white rounded-lg border border-zen-light-green/40 p-3">
        <h2 className="text-xs uppercase font-semibold tracking-wider text-zen-dark-green mb-2">
          Vendor × Cohort heatmap
        </h2>
        {!heatmap || heatmap.vendors.length === 0 ? (
          <div className="text-xs text-zen-dark-teal/60 italic">
            No vendor data yet. Click <strong>Refresh</strong> to ingest from technographic seeds.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="text-xs">
              <thead className="text-zen-dark-teal/70">
                <tr>
                  <th className="text-left px-2 py-1">Vendor</th>
                  {heatmap.cohorts.map((c) => (
                    <th key={c} className="text-right px-2 py-1 font-mono text-[10px]">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {heatmap.vendors.map((vid) => {
                  const profile = (vendors || []).find((v) => v.vendor_id === vid);
                  return (
                    <tr key={vid} className={`hover:bg-zen-white-green/40 ${selected === vid ? 'bg-zen-white-green' : ''}`}>
                      <td className="px-2 py-1">
                        <button
                          onClick={() => setSelected(selected === vid ? null : vid)}
                          className="text-zen-dark-green hover:text-zen-teal text-left"
                        >
                          {profile?.name || vid}
                        </button>
                        {profile?.category && (
                          <span className="ml-2 text-[10px] uppercase rounded px-1 bg-zen-light-green/40 text-zen-dark-teal">
                            {profile.category}
                          </span>
                        )}
                      </td>
                      {heatmap.cohorts.map((cid) => {
                        const cell = cellByKey.get(`${vid}__${cid}`);
                        if (!cell || cell.adoption_pct === 0) {
                          return <td key={cid} className="text-right px-2 py-1 text-zen-dark-teal/40">·</td>;
                        }
                        const pct = cell.adoption_pct;
                        const intensity = Math.min(1, pct / 100);
                        return (
                          <td
                            key={cid}
                            className="text-right px-2 py-1 font-mono text-[10px]"
                            style={{
                              backgroundColor: `rgba(20, 116, 110, ${0.10 + intensity * 0.50})`,
                              color: intensity > 0.5 ? 'white' : '#1C4A4D',
                            }}
                            title={`${cell.adopters.join(', ')} of ${cell.cohort_size}`}
                          >
                            {pct.toFixed(0)}%
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <div className="bg-white rounded-lg border border-zen-light-green/40 p-3">
          <h2 className="text-xs uppercase font-semibold tracking-wider text-zen-dark-green mb-2">
            Vendor profiles ({(vendors || []).length})
          </h2>
          <ul className="divide-y divide-zen-light-green/30 max-h-[640px] overflow-auto">
            {(vendors || []).map((v) => (
              <li
                key={v.vendor_id}
                className={`py-2 cursor-pointer hover:bg-zen-white-green/50 rounded px-1 ${selected === v.vendor_id ? 'bg-zen-white-green' : ''}`}
                onClick={() => setSelected(selected === v.vendor_id ? null : v.vendor_id)}
              >
                <div className="flex items-center gap-2 text-xs">
                  <span className="font-medium text-zen-dark-green">{v.name}</span>
                  {v.category && (
                    <span className="text-[10px] uppercase rounded px-1 bg-zen-light-green/40 text-zen-dark-teal">
                      {v.category}
                    </span>
                  )}
                  <span className="ml-auto text-[10px] text-zen-dark-teal/70">
                    conf {(v.avg_confidence * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="text-[10px] text-zen-dark-teal/70 mt-0.5 flex flex-wrap gap-x-2">
                  <span className="inline-flex items-center gap-0.5"><Building2 size={9} />{v.companies.length} companies</span>
                  <span>{v.cohorts.length} cohorts</span>
                  <span>{v.news_mentions} news</span>
                  {v.ai_signal_avg != null && <span>AI {v.ai_signal_avg}</span>}
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div className="bg-white rounded-lg border border-zen-light-green/40 p-3">
          <h2 className="text-xs uppercase font-semibold tracking-wider text-zen-dark-green mb-2">
            Events {selected && <span className="text-zen-dark-teal/60 normal-case font-normal">— filtered</span>}
          </h2>
          <ul className="divide-y divide-zen-light-green/30 max-h-[640px] overflow-auto">
            {(events || []).slice(0, 50).map((e) => (
              <li key={e.id} className="py-2 text-xs">
                <div className="flex items-center gap-2 text-[10px] text-zen-dark-teal/70">
                  <span className="font-mono">{e.vendor_name}</span>
                  <span>·</span>
                  <span className="uppercase">{e.kind}</span>
                  {e.url && (
                    <a href={e.url} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-0.5 text-zen-teal hover:text-zen-dark-teal">
                      source <ExternalLink size={9} />
                    </a>
                  )}
                </div>
                <div className="font-medium text-zen-dark-green mt-0.5">{e.title}</div>
                <div className="text-[10px] text-zen-dark-teal/60 mt-0.5">
                  {e.published_at && new Date(e.published_at).toLocaleDateString()} {' · '} {e.source}
                </div>
              </li>
            ))}
            {(events || []).length === 0 && (
              <li className="text-zen-dark-teal/60 italic text-xs py-1">No events for this filter.</li>
            )}
          </ul>
        </div>
      </div>
    </div>
  );
}
