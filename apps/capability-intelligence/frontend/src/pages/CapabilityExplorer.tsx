import { useQuery } from '@tanstack/react-query';
import { Search, X } from 'lucide-react';
import { apiGet, type Tree } from '@/lib/api';
import CatalogueSunburst from '@/components/CatalogueSunburst';
import CatalogueTree from '@/components/CatalogueTree';
import { useFilters } from '@/store/filters';

export default function CapabilityExplorer() {
  const { pillarId, categoryId, search, setPillar, setCategory, setSearch, reset } = useFilters();
  const params = pillarId ? `?pillar_id=${encodeURIComponent(pillarId)}` : '';

  const { data, isLoading, error } = useQuery<Tree>({
    queryKey: ['catalogue-tree', pillarId],
    queryFn: () => apiGet<Tree>(`/catalogue/tree${params}`),
  });

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
        <p className="text-sm text-zen-dark-teal/80">
          Click a slice to drill in; double-click a subcap to open Subcap Deep Dive.
        </p>
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

      {isLoading && <div className="text-xs text-zen-dark-teal/60">Loading…</div>}
      {error && <div className="text-xs text-zen-orange">Failed to load tree.</div>}

      {filtered && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="bg-white rounded-lg shadow-sm border border-zen-light-green/40 p-3 flex items-center justify-center min-h-[560px]">
            <CatalogueSunburst tree={filtered} />
          </div>
          <div className="bg-white rounded-lg shadow-sm border border-zen-light-green/40 p-2 max-h-[640px] overflow-auto">
            <CatalogueTree tree={filtered} search={search} />
          </div>
        </div>
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
