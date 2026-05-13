import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Layers, PieChart, Search, X } from 'lucide-react';
import { apiGet, type Tree } from '@/lib/api';
import CatalogueSunburst from '@/components/CatalogueSunburst';
import CatalogueTree from '@/components/CatalogueTree';
import PillarBreakdown, { type Structure } from '@/components/PillarBreakdown';
import { useFilters } from '@/store/filters';

type MaturityDist = {
  total_with_maturity: number;
  by_level: Record<string, number>;
  labels: Record<string, string>;
};

const MATURITY_BANDS: { key: string; bg: string; accent: string }[] = [
  { key: 'm1', bg: 'bg-zen-light-orange/60', accent: 'text-zen-orange' },
  { key: 'm2', bg: 'bg-zen-purple-grey/60', accent: 'text-zen-dark-purple' },
  { key: 'm3', bg: 'bg-zen-light-blue/40', accent: 'text-zen-blue' },
  { key: 'm4', bg: 'bg-zen-ice', accent: 'text-zen-light-teal' },
  { key: 'm5', bg: 'bg-zen-light-green/70', accent: 'text-zen-teal' },
];

type ViewMode = 'hierarchy' | 'sunburst';

export default function CapabilityExplorer() {
  const { pillarId, categoryId, search, setPillar, setCategory, setSearch, reset } = useFilters();
  const params = pillarId ? `?pillar_id=${encodeURIComponent(pillarId)}` : '';
  const [view, setView] = useState<ViewMode>('hierarchy');

  const { data: maturityDist } = useQuery<MaturityDist>({
    queryKey: ['maturity-dist', pillarId],
    queryFn: () => apiGet<MaturityDist>(`/catalogue/maturity-distribution${params}`),
  });

  const { data, isLoading, error } = useQuery<Tree>({
    queryKey: ['catalogue-tree', pillarId],
    queryFn: () => apiGet<Tree>(`/catalogue/tree${params}`),
    enabled: view === 'sunburst',
  });

  const { data: structure } = useQuery<Structure>({
    queryKey: ['catalogue-structure', pillarId],
    queryFn: () => apiGet<Structure>('/catalogue/structure'),
    enabled: view === 'hierarchy',
  });

  // When a pillar filter is set, slice the structure down to that one
  // pillar so the hierarchy view stays focused.
  const structureFiltered: Structure | undefined =
    structure && pillarId
      ? {
          ...structure,
          pillars: structure.pillars.filter((p) => p.pillar_id === pillarId),
        }
      : structure;

  const filtered: Tree | undefined = data && categoryId
    ? {
        pillars: data.pillars.map((p) => ({
          ...p,
          categories: p.categories.filter((c) => c.category_id === categoryId),
        })),
      }
    : data;

  const hasFilter = !!(pillarId || categoryId || search);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-zen-dark-green">Capability Explorer</h1>
        <p className="text-sm text-zen-dark-teal/80 max-w-3xl">
          Two ways to navigate the four-pillar catalogue. <b>Hierarchy</b> shows the
          Pillar → Category → L1 → Subcap structure with counts at every level. <b>Sunburst</b>
          renders the same tree visually; double-click a subcap slice to deep-dive.
        </p>
      </div>

      {/* View toggle */}
      <div className="inline-flex items-center bg-zen-ice rounded-lg border border-zen-separator p-0.5">
        {([
          { key: 'hierarchy', label: 'Hierarchy', Icon: Layers },
          { key: 'sunburst', label: 'Sunburst', Icon: PieChart },
        ] as { key: ViewMode; label: string; Icon: typeof Layers }[]).map((v) => (
          <button
            key={v.key}
            type="button"
            onClick={() => setView(v.key)}
            className={`inline-flex items-center gap-1.5 text-xs px-3 py-1 rounded ${
              view === v.key
                ? 'bg-white shadow-sm text-zen-dark-green font-medium'
                : 'text-zen-text-gray'
            }`}
          >
            <v.Icon size={12} />
            {v.label}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2 bg-white rounded-lg border border-zen-light-green/40 p-2">
        <div className="flex items-center gap-1 flex-1 min-w-[200px]">
          <Search size={14} className="text-zen-dark-teal/60" />
          <input
            type="text"
            placeholder="Filter subcaps by name or ID…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="bg-transparent text-sm outline-none flex-1 placeholder:text-zen-dark-teal/40"
          />
        </div>
        {pillarId && (
          <Chip label={`Pillar: ${pillarId}`} onClear={() => setPillar(null)} />
        )}
        {categoryId && (
          <Chip label={`Category: ${categoryId}`} onClear={() => setCategory(null)} />
        )}
        {hasFilter && (
          <button
            type="button"
            onClick={reset}
            className="text-xs text-zen-dark-teal hover:text-zen-dark-green underline"
          >
            Reset filters
          </button>
        )}
      </div>

      {/* Maturity-distribution band — quick at-a-glance ladder coverage */}
      {maturityDist && maturityDist.total_with_maturity > 0 && (
        <div className="bg-white rounded-lg border border-zen-separator p-3">
          <div className="text-[10px] uppercase tracking-wider text-zen-muted-text mb-2">
            Maturity ladder coverage · {maturityDist.total_with_maturity} subcaps with descriptors
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
            {MATURITY_BANDS.map((b) => {
              const count = maturityDist.by_level[b.key] || 0;
              const label = maturityDist.labels[b.key] || b.key.toUpperCase();
              return (
                <div key={b.key} className={`${b.bg} rounded p-2`}>
                  <div className={`text-[10px] uppercase tracking-wider font-semibold ${b.accent}`}>
                    {label}
                  </div>
                  <div className="text-xl font-semibold text-zen-dark-green mt-0.5">{count}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* HIERARCHY VIEW */}
      {view === 'hierarchy' && structureFiltered && (
        <PillarBreakdown data={structureFiltered} />
      )}

      {/* SUNBURST VIEW (existing) */}
      {view === 'sunburst' && (
        <>
          {isLoading && <div className="text-xs text-zen-muted-text">Loading…</div>}
          {error && <div className="text-xs text-zen-orange">Failed to load tree.</div>}
          {filtered && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 md:gap-4">
              <div className="bg-white rounded-lg shadow-sm border border-zen-separator p-3 flex items-center justify-center min-h-[400px] md:min-h-[560px]">
                <CatalogueSunburst tree={filtered} />
              </div>
              <div className="bg-white rounded-lg shadow-sm border border-zen-separator p-2 max-h-[480px] md:max-h-[640px] overflow-auto">
                <CatalogueTree tree={filtered} search={search} />
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function Chip({ label, onClear }: { label: string; onClear: () => void }) {
  return (
    <span className="text-xs bg-zen-light-green/60 text-zen-dark-green rounded-full pl-2 pr-1 py-0.5 inline-flex items-center gap-1">
      {label}
      <button onClick={onClear} aria-label={`clear ${label}`} className="hover:text-zen-orange">
        <X size={12} />
      </button>
    </span>
  );
}
