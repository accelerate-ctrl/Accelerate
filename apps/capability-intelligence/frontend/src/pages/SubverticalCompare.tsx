import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { apiGet, type Subcap, type SubverticalCompare as SCResp } from '@/lib/api';

export default function SubverticalCompare() {
  const [params, setParams] = useSearchParams();
  const initial = params.get('id') || 'P1C1.1.1';
  const [id, setId] = useState(initial);

  const { data: subcaps } = useQuery<Subcap[]>({
    queryKey: ['subcaps-list'],
    queryFn: () => apiGet<Subcap[]>('/catalogue/subcaps'),
  });

  const { data, isLoading } = useQuery<SCResp>({
    queryKey: ['sv-compare', id],
    queryFn: () => apiGet<SCResp>(`/lens/subvertical-compare/${encodeURIComponent(id)}`),
    enabled: !!id,
  });

  const onSelect = (newId: string) => {
    setId(newId);
    setParams({ id: newId });
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-zen-dark-green">Subvertical Compare</h1>
        <p className="text-sm text-zen-dark-teal/80">
          For a given subcap, see which value-chain stages apply across the 10 subverticals.
        </p>
      </div>

      <div className="bg-white rounded-lg border border-zen-light-green/40 p-3 flex items-center gap-2 text-sm">
        <label className="text-zen-dark-teal/70">Subcap</label>
        <select
          value={id}
          onChange={(e) => onSelect(e.target.value)}
          className="border border-zen-light-green rounded px-2 py-1 text-xs flex-1 max-w-md"
        >
          {subcaps?.slice(0, 500).map((s) => (
            <option key={s.sub_cap_id} value={s.sub_cap_id}>
              {s.sub_cap_id} — {s.sub_cap_name}
            </option>
          ))}
        </select>
      </div>

      {isLoading && <div className="text-xs text-zen-dark-teal/60">Loading…</div>}

      {data && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {data.rows.map((row) => (
            <div
              key={row.subvertical_code}
              className={`bg-white rounded-lg border p-3 ${row.applicable ? 'border-zen-light-green/40' : 'border-zen-light-green/20 opacity-60'}`}
            >
              <div className="flex items-center justify-between mb-1">
                <div>
                  <span className="font-mono text-[10px] bg-zen-dark-green text-white rounded px-1.5 py-0.5 mr-2">
                    {row.subvertical_code}
                  </span>
                  <span className="text-sm font-semibold text-zen-dark-green">{row.subvertical_name}</span>
                </div>
                {!row.applicable && <span className="text-[10px] text-zen-dark-teal/60 italic">N/A</span>}
              </div>
              {row.stages.length > 0 && (
                <ul className="space-y-0.5">
                  {row.stages.map((s, i) => (
                    <li key={i} className="text-xs text-zen-dark-teal flex items-center gap-2">
                      <span className="font-mono text-[9px] bg-zen-light-green/50 rounded px-1">{s.cluster}</span>
                      <span className="flex-1 truncate">{s.name}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
