import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { apiGet, type MaturityHeatmap as MH, type Pillar } from '@/lib/api';

const FILL_COLORS = ['#e8f7f6', '#b0eed3', '#62d7b8', '#27bbaf', '#185f60'];

export default function MaturityHeatmap() {
  const [pillar, setPillar] = useState<string>('P1');

  const { data: pillars } = useQuery<Pillar[]>({
    queryKey: ['pillars'],
    queryFn: () => apiGet<Pillar[]>('/catalogue/pillars'),
  });

  const { data, isLoading } = useQuery<MH>({
    queryKey: ['maturity', pillar],
    queryFn: () => apiGet<MH>(`/lens/maturity-heatmap?pillar_id=${pillar}`),
    enabled: !!pillar,
  });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-zen-dark-green">Maturity Heatmap</h1>
        <p className="text-sm text-zen-dark-teal/80">
          Each row = subcap; each cell shaded by descriptor depth. Empty cells highlight maturity
          gaps. Benchmark / peer overlay arrives in Batch 5.
        </p>
      </div>

      <div className="bg-white rounded-lg border border-zen-light-green/40 p-3 flex items-center gap-3 text-sm">
        <label className="text-zen-dark-teal/70">Pillar</label>
        <select
          value={pillar}
          onChange={(e) => setPillar(e.target.value)}
          className="border border-zen-light-green rounded px-2 py-1 text-xs"
        >
          {pillars?.map((p) => (
            <option key={p.pillar_id} value={p.pillar_id}>
              {p.pillar_id} — {p.name}
            </option>
          ))}
        </select>
      </div>

      {isLoading && <div className="text-xs text-zen-dark-teal/60">Loading…</div>}

      {data && (
        <div className="bg-white rounded-lg border border-zen-light-green/40 overflow-auto">
          <table className="text-xs w-full">
            <thead className="sticky top-0 bg-zen-white-green">
              <tr>
                <th className="text-left px-2 py-1 text-zen-dark-teal/70">Sub_Cap_ID</th>
                <th className="text-left px-2 py-1 text-zen-dark-teal/70">Subcap</th>
                {data.levels.map((lvl) => (
                  <th key={lvl} className="px-2 py-1 text-zen-dark-teal/70 text-center">
                    {lvl}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.slice(0, 250).map((r) => (
                <tr key={r.sub_cap_id} className="border-t border-zen-light-green/20 hover:bg-zen-white-green">
                  <td className="px-2 py-0.5 font-mono text-[10px] text-zen-dark-teal">
                    <Link to={`/subcap?id=${encodeURIComponent(r.sub_cap_id)}`} className="hover:text-zen-dark-green">
                      {r.sub_cap_id}
                    </Link>
                  </td>
                  <td className="px-2 py-0.5 text-zen-dark-green truncate max-w-[280px]" title={r.sub_cap_name}>
                    {r.sub_cap_name}
                  </td>
                  {r.cells.map((c, i) => (
                    <td
                      key={c.level}
                      className="px-1 py-0.5 text-center"
                      title={c.preview}
                      style={{
                        backgroundColor: c.filled ? FILL_COLORS[i] : '#F5F5F5',
                        color: i >= 3 ? 'white' : '#1c4a4d',
                      }}
                    >
                      {c.filled ? '●' : '·'}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {data.rows.length > 250 && (
            <div className="text-[10px] text-zen-dark-teal/60 px-2 py-1">
              Showing first 250 of {data.rows.length} rows. Filter / pagination land in Batch 8.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
