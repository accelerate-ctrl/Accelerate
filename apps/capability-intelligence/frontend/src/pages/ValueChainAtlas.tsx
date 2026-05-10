import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { apiGet, type Subvertical, type ValueChainAtlas as Atlas } from '@/lib/api';

export default function ValueChainAtlas() {
  const [subvertical, setSubvertical] = useState<string>('');
  const { data: subverticals } = useQuery<Subvertical[]>({
    queryKey: ['subverticals'],
    queryFn: () => apiGet<Subvertical[]>('/lens/subverticals'),
  });

  const { data: atlas, isLoading } = useQuery<Atlas>({
    queryKey: ['atlas', subvertical],
    queryFn: () => apiGet<Atlas>(`/lens/value-chain-atlas${subvertical ? `?subvertical_code=${subvertical}` : ''}`),
  });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-zen-dark-green">Value Chain Atlas</h1>
        <p className="text-sm text-zen-dark-teal/80">
          8 universal MECE clusters with subvertical-specific stages mapped underneath.
          Stage names that don't match any cluster keyword fall to <span className="font-mono">VCC-00</span> for review.
        </p>
      </div>

      <div className="bg-white rounded-lg border border-zen-light-green/40 p-3 flex items-center gap-3 text-sm">
        <label className="text-zen-dark-teal/70">Subvertical lens</label>
        <select
          value={subvertical}
          onChange={(e) => setSubvertical(e.target.value)}
          className="border border-zen-light-green rounded px-2 py-1 text-xs"
        >
          <option value="">All 10</option>
          {subverticals?.map((sv) => (
            <option key={sv.code} value={sv.code}>
              {sv.code} — {sv.name}
            </option>
          ))}
        </select>
      </div>

      {isLoading && <div className="text-xs text-zen-dark-teal/60">Loading atlas…</div>}

      {atlas && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
          {atlas.clusters.map((c) => (
            <div
              key={c.code}
              className="bg-white rounded-lg border border-zen-light-green/40 p-3"
              style={{ borderLeftWidth: 4, borderLeftColor: c.color || '#27bbaf' }}
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-zen-dark-teal/60 font-mono">{c.code}</div>
                  <div className="text-sm font-semibold text-zen-dark-green">{c.name}</div>
                </div>
                <div className="text-right">
                  <div className="text-xs text-zen-dark-teal/70">subcaps</div>
                  <div className="font-semibold text-zen-dark-green">{c.total_subcaps}</div>
                </div>
              </div>
              {c.stages.length === 0 ? (
                <div className="text-[10px] text-zen-dark-teal/50 italic mt-2">no stages mapped</div>
              ) : (
                <ul className="mt-2 space-y-1 max-h-72 overflow-auto">
                  {c.stages.slice(0, 30).map((s, i) => (
                    <li key={i} className="text-[11px] text-zen-dark-teal flex items-center gap-1">
                      <span className="font-mono text-[9px] bg-zen-light-green/50 text-zen-dark-teal rounded px-1">
                        {s.subvertical_code}
                      </span>
                      <span className="flex-1 truncate" title={s.name}>{s.name}</span>
                      <span className="text-[10px] text-zen-dark-teal/60">×{s.subcap_count}</span>
                    </li>
                  ))}
                  {c.stages.length > 30 && (
                    <li className="text-[10px] text-zen-dark-teal/60">… and {c.stages.length - 30} more</li>
                  )}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
