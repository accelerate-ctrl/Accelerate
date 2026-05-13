import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { apiGet, type Pillar } from '@/lib/api';

// Per-level cell fills are the Zennify M1→M5 gradient (Foundational →
// Transformational) from the ZDS color authority. Empty cells are the
// canonical light-bg.
const CELL_FILL = ['#FFCB99', '#C7D3EC', '#E6F3FA', '#B0EDD3', '#27BBAF'];
const CELL_TEXT = ['#1C4A4D', '#1C4A4D', '#1C4A4D', '#1C4A4D', '#FFFFFF'];
const EMPTY_CELL = '#F5F5F5';

// ZDS 4-tier maturity bands (Activating / Building / Competing /
// Differentiating) — the marketing colour system. The Heatmap uses these
// on the row-label chip so operators see at a glance which tier each
// subcap currently sits in.
const ZDS_BAND_STYLE: Record<string, { bg: string; text: string; label: string }> = {
  activating: { bg: '#FFF3E8', text: '#F97316', label: 'Activating' },
  building: { bg: '#F2F4F9', text: '#4E5E8A', label: 'Building' },
  competing: { bg: '#E6F5F3', text: '#198478', label: 'Competing' },
  differentiating: { bg: '#E8F7F6', text: '#185F60', label: 'Differentiating' },
};

type Cell = { level: string; filled: boolean; preview: string };
type Row = {
  sub_cap_id: string;
  sub_cap_name: string;
  category_id?: string;
  l1_capability?: string;
  current_level: number;
  benchmark_level: number | null;
  gap: number | null;
  zds_band: string | null;
  cells: Cell[];
};
type Cohort = {
  cohort_id: string;
  name?: string;
  subvertical_code?: string;
};
type Heatmap = {
  pillar_id: string | null;
  cohort_id: string | null;
  cohort_observations: number;
  sort: string;
  levels: string[];
  bands: { key: string; label: string; tier_range: [number, number] }[];
  rows: Row[];
};

export default function MaturityHeatmap() {
  const [pillar, setPillar] = useState<string>('P1');
  const [cohortId, setCohortId] = useState<string>('');
  const [sort, setSort] = useState<'category' | 'gap'>('category');

  const { data: pillars } = useQuery<Pillar[]>({
    queryKey: ['pillars'],
    queryFn: () => apiGet<Pillar[]>('/catalogue/pillars'),
  });

  const { data: cohorts } = useQuery<Cohort[]>({
    queryKey: ['benchmark-cohorts'],
    queryFn: () => apiGet<Cohort[]>('/lens/cohorts'),
  });

  const { data, isLoading } = useQuery<Heatmap>({
    queryKey: ['maturity', pillar, cohortId, sort],
    queryFn: () => {
      const params = new URLSearchParams({ pillar_id: pillar, sort });
      if (cohortId) params.set('cohort_id', cohortId);
      return apiGet<Heatmap>(`/lens/maturity-heatmap?${params.toString()}`);
    },
    enabled: !!pillar,
  });

  const hasCohort = !!cohortId && (data?.cohort_observations ?? 0) > 0;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-zen-dark-green">Maturity Heatmap</h1>
        <p className="text-sm text-zen-dark-teal/80 max-w-3xl">
          Every subcap × five M-bands (Foundational → Transformational). Each row also carries a
          ZDS maturity-tier badge so you can spot the four-band picture at a glance. Pick a
          benchmark cohort to overlay peer medians and sort by the biggest gaps.
        </p>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-lg border border-zen-separator p-3 flex flex-wrap items-center gap-3 text-sm">
        <label className="flex items-center gap-1 text-zen-text-gray">
          <span>Pillar</span>
          <select
            value={pillar}
            onChange={(e) => setPillar(e.target.value)}
            className="border border-zen-separator rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-zen-teal"
          >
            {pillars?.map((p) => (
              <option key={p.pillar_id} value={p.pillar_id}>
                {p.pillar_id} — {p.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1 text-zen-text-gray">
          <span>Benchmark cohort</span>
          <select
            value={cohortId}
            onChange={(e) => {
              setCohortId(e.target.value);
              if (!e.target.value && sort === 'gap') setSort('category');
            }}
            className="border border-zen-separator rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-zen-teal"
          >
            <option value="">— none —</option>
            {(cohorts || []).map((c) => (
              <option key={c.cohort_id} value={c.cohort_id}>
                {c.subvertical_code ? `${c.subvertical_code} · ` : ''}
                {c.name || c.cohort_id}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1 text-zen-text-gray">
          <span>Sort</span>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as 'category' | 'gap')}
            className="border border-zen-separator rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-zen-teal"
            disabled={!hasCohort && sort !== 'category'}
          >
            <option value="category">Category order</option>
            <option value="gap" disabled={!hasCohort}>
              Largest gap first {hasCohort ? '' : '(needs cohort)'}
            </option>
          </select>
        </label>
        {cohortId && !hasCohort && (
          <div className="text-[11px] text-zen-orange">
            No benchmark observations for this cohort yet — falling back to descriptor-only view.
          </div>
        )}
      </div>

      {/* ZDS 4-band legend */}
      <div className="bg-white rounded-lg border border-zen-separator p-3">
        <div className="text-[10px] uppercase tracking-wider text-zen-muted-text mb-2">
          Zennify 4-tier maturity bands
        </div>
        <div className="flex flex-wrap gap-2">
          {Object.entries(ZDS_BAND_STYLE).map(([k, s]) => (
            <span
              key={k}
              className="text-[11px] rounded px-2 py-0.5 font-medium"
              style={{ backgroundColor: s.bg, color: s.text }}
            >
              {s.label}
            </span>
          ))}
          <span className="text-[11px] text-zen-muted-text ml-auto">
            Cells use the M1 → M5 fill gradient
          </span>
        </div>
      </div>

      {isLoading && <div className="text-xs text-zen-muted-text">Loading…</div>}

      {data && (
        <div className="bg-white rounded-lg border border-zen-separator overflow-auto">
          <table className="text-xs w-full">
            <thead className="sticky top-0 bg-zen-ice z-10">
              <tr>
                <th className="text-left px-2 py-1 text-zen-text-gray">Sub_Cap_ID</th>
                <th className="text-left px-2 py-1 text-zen-text-gray">Subcap</th>
                <th className="px-2 py-1 text-zen-text-gray text-center">Band</th>
                {data.levels.map((lvl) => (
                  <th key={lvl} className="px-2 py-1 text-zen-text-gray text-center">
                    {lvl}
                  </th>
                ))}
                {hasCohort && (
                  <>
                    <th className="px-2 py-1 text-zen-text-gray text-center">Bench</th>
                    <th className="px-2 py-1 text-zen-text-gray text-center">Gap</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {data.rows.slice(0, 250).map((r) => {
                const bandStyle = r.zds_band ? ZDS_BAND_STYLE[r.zds_band] : null;
                return (
                  <tr
                    key={r.sub_cap_id}
                    className="border-t border-zen-separator/40 hover:bg-zen-ice/40"
                  >
                    <td className="px-2 py-0.5 font-mono text-[10px] text-zen-teal">
                      <Link
                        to={`/subcap?id=${encodeURIComponent(r.sub_cap_id)}`}
                        className="hover:text-zen-dark-green"
                      >
                        {r.sub_cap_id}
                      </Link>
                    </td>
                    <td
                      className="px-2 py-0.5 text-zen-dark-green truncate max-w-[280px]"
                      title={r.sub_cap_name}
                    >
                      {r.sub_cap_name}
                    </td>
                    <td className="px-2 py-0.5 text-center">
                      {bandStyle ? (
                        <span
                          className="text-[10px] rounded px-1.5 py-0.5 font-medium"
                          style={{ backgroundColor: bandStyle.bg, color: bandStyle.text }}
                        >
                          {bandStyle.label}
                        </span>
                      ) : (
                        <span className="text-[10px] text-zen-muted-text italic">—</span>
                      )}
                    </td>
                    {r.cells.map((c, i) => (
                      <td
                        key={c.level}
                        className="px-1 py-0.5 text-center"
                        title={c.preview}
                        style={{
                          backgroundColor: c.filled ? CELL_FILL[i] : EMPTY_CELL,
                          color: c.filled ? CELL_TEXT[i] : '#9CA3AF',
                        }}
                      >
                        {c.filled ? '●' : '·'}
                      </td>
                    ))}
                    {hasCohort && (
                      <>
                        <td className="px-2 py-0.5 text-center text-zen-text-gray">
                          {r.benchmark_level ?? '—'}
                        </td>
                        <td
                          className="px-2 py-0.5 text-center font-semibold"
                          style={{
                            color:
                              r.gap == null
                                ? '#9CA3AF'
                                : r.gap < 0
                                  ? '#C25008'
                                  : r.gap > 0
                                    ? '#059669'
                                    : '#6B7280',
                          }}
                        >
                          {r.gap == null ? '—' : r.gap > 0 ? `+${r.gap}` : r.gap}
                        </td>
                      </>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
          {data.rows.length > 250 && (
            <div className="text-[10px] text-zen-muted-text px-2 py-1">
              Showing first 250 of {data.rows.length} rows.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
