// PillarBreakdown — collapsible hierarchical view of the catalogue
// (Pillar → Category → L1 capability → Subcap). Drives Mission Control
// and the Capability Explorer's "Hierarchy" tab.
//
// Design choices:
//   * Per-pillar accordion at the top (P1/P2/P3/P4) so the page isn't
//     overwhelming on first load — only the active pillar is expanded.
//   * Inside a pillar, categories are shown as side-by-side cards on
//     ≥ md and stacked on mobile.
//   * L1 capabilities live inside each category and expand on click to
//     reveal individual subcaps.
//   * Counts surface at every level so operators see the structure at
//     a glance.
//   * Active vs inactive subcap badges (Zennify Toggle Control Panel
//     semantics) are visible at the L1 level.

import { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, Layers } from 'lucide-react';
import { Link } from 'react-router-dom';

export type StructureSubcap = {
  sub_cap_id: string;
  sub_cap_name?: string;
  zennify_status?: string;
};
export type StructureL1 = {
  l1_capability: string;
  subcap_count: number;
  active_subcap_count: number;
  subcaps: StructureSubcap[];
};
export type StructureCategory = {
  category_id: string;
  name: string;
  subcap_total: number;
  l1_total: number;
  l1s: StructureL1[];
};
export type StructurePillar = {
  pillar_id: string;
  name: string;
  schema_status?: string;
  version?: string;
  source_file_name?: string;
  subcap_total: number;
  l1_total: number;
  category_total: number;
  categories: StructureCategory[];
};
export type Structure = {
  pillars: StructurePillar[];
  totals: { pillars: number; subcaps: number; l1s: number; categories: number };
};

const PILLAR_ACCENT: Record<string, string> = {
  P1: 'border-l-zen-teal',
  P2: 'border-l-zen-dark-teal',
  P3: 'border-l-zen-accent-green',
  P4: 'border-l-zen-light-teal',
};

const PILLAR_BG: Record<string, string> = {
  P1: 'bg-zen-light-green/30',
  P2: 'bg-zen-ice',
  P3: 'bg-zen-mint/30',
  P4: 'bg-zen-light-green/50',
};

export default function PillarBreakdown({ data }: { data: Structure }) {
  const initialOpen = useMemo(
    () => new Set(data.pillars.slice(0, 1).map((p) => p.pillar_id)),
    [data.pillars],
  );
  const [openPillars, setOpenPillars] = useState<Set<string>>(initialOpen);

  const togglePillar = (pid: string) => {
    setOpenPillars((prev) => {
      const next = new Set(prev);
      if (next.has(pid)) next.delete(pid);
      else next.add(pid);
      return next;
    });
  };

  if (!data.pillars || data.pillars.length === 0) {
    return (
      <div className="bg-white rounded-lg border border-zen-separator p-6 text-center text-sm text-zen-text-gray">
        No pillars ingested yet. Click <b>Pull sources</b> (top-right) to fetch
        Pillar 1–4 workbooks from Drive.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {data.pillars.map((p) => {
        const isOpen = openPillars.has(p.pillar_id);
        return (
          <section
            key={p.pillar_id}
            className={`bg-white rounded-lg border border-zen-separator border-l-4 ${
              PILLAR_ACCENT[p.pillar_id] || 'border-l-zen-teal'
            }`}
          >
            <button
              type="button"
              onClick={() => togglePillar(p.pillar_id)}
              className="w-full flex flex-wrap items-center gap-2 md:gap-3 px-3 md:px-4 py-3 hover:bg-zen-ice/40 transition-colors text-left"
              aria-expanded={isOpen}
            >
              {isOpen ? (
                <ChevronDown size={16} className="text-zen-teal shrink-0" />
              ) : (
                <ChevronRight size={16} className="text-zen-teal shrink-0" />
              )}
              <span className="font-mono text-xs bg-zen-dark-green text-white rounded px-1.5 py-0.5">
                {p.pillar_id}
              </span>
              <h2 className="text-sm md:text-base font-semibold text-zen-dark-green truncate">
                {p.name}
              </h2>
              {p.version && (
                <span className="text-[10px] text-zen-muted-text font-mono">{p.version}</span>
              )}
              <div className="ml-auto hidden sm:flex items-center gap-3 md:gap-4 text-[11px] md:text-xs text-zen-text-gray">
                <CountBadge label="categories" value={p.category_total} />
                <CountBadge label="L1 capabilities" value={p.l1_total} />
                <CountBadge label="subcaps" value={p.subcap_total} accent />
              </div>
            </button>

            {/* Mobile-only counts row */}
            <div className="sm:hidden flex flex-wrap gap-2 px-4 pb-2 text-[10px] text-zen-text-gray">
              <CountBadge label="cats" value={p.category_total} />
              <CountBadge label="L1s" value={p.l1_total} />
              <CountBadge label="subcaps" value={p.subcap_total} accent />
            </div>

            {isOpen && (
              <div className={`px-3 md:px-4 pb-4 pt-1 grid grid-cols-1 md:grid-cols-2 gap-3`}>
                {p.categories.map((c) => (
                  <CategoryCard
                    key={c.category_id}
                    cat={c}
                    bg={PILLAR_BG[p.pillar_id] || 'bg-zen-ice'}
                  />
                ))}
                {p.categories.length === 0 && (
                  <div className="text-xs text-zen-muted-text italic col-span-full">
                    No categories ingested for this pillar yet.
                  </div>
                )}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}

function CountBadge({
  label,
  value,
  accent = false,
}: {
  label: string;
  value: number;
  accent?: boolean;
}) {
  return (
    <span className="inline-flex items-baseline gap-1 whitespace-nowrap">
      <span
        className={`font-mono ${accent ? 'text-zen-teal font-semibold' : 'text-zen-dark-green'}`}
      >
        {value}
      </span>
      <span className="text-zen-muted-text">{label}</span>
    </span>
  );
}

function CategoryCard({ cat, bg }: { cat: StructureCategory; bg: string }) {
  const [openL1s, setOpenL1s] = useState<Set<string>>(new Set());
  const toggle = (l1: string) =>
    setOpenL1s((prev) => {
      const next = new Set(prev);
      if (next.has(l1)) next.delete(l1);
      else next.add(l1);
      return next;
    });

  return (
    <article className={`rounded-lg ${bg} p-3`}>
      <header className="flex items-baseline gap-2 mb-2">
        <span className="font-mono text-[10px] text-zen-muted-text">{cat.category_id}</span>
        <h3 className="text-sm font-semibold text-zen-dark-green truncate flex-1">{cat.name}</h3>
        <span className="text-[10px] text-zen-text-gray">
          {cat.l1_total} L1 · {cat.subcap_total} subs
        </span>
      </header>
      <ul className="divide-y divide-zen-separator/40 bg-white rounded">
        {cat.l1s.map((l1) => {
          const isOpen = openL1s.has(l1.l1_capability);
          const inactive = l1.subcap_count - l1.active_subcap_count;
          return (
            <li key={l1.l1_capability}>
              <button
                type="button"
                onClick={() => toggle(l1.l1_capability)}
                className="w-full px-2 py-1.5 text-left flex items-center gap-1.5 hover:bg-zen-ice/50 transition-colors"
                aria-expanded={isOpen}
              >
                {isOpen ? (
                  <ChevronDown size={12} className="text-zen-teal" />
                ) : (
                  <ChevronRight size={12} className="text-zen-teal" />
                )}
                <Layers size={11} className="text-zen-muted-text" />
                <span className="text-xs font-medium text-zen-dark-green flex-1 truncate">
                  {l1.l1_capability}
                </span>
                <span className="text-[10px] font-mono text-zen-text-gray">
                  {l1.active_subcap_count}/{l1.subcap_count}
                </span>
                {inactive > 0 && (
                  <span
                    className="text-[9px] text-zen-orange ml-1"
                    title={`${inactive} inactive subcaps`}
                  >
                    {inactive}↓
                  </span>
                )}
              </button>
              {isOpen && (
                <ul className="bg-zen-ice/40 border-t border-zen-separator/40">
                  {l1.subcaps.map((s) => (
                    <li key={s.sub_cap_id} className="px-2 py-1">
                      <Link
                        to={`/subcap?id=${encodeURIComponent(s.sub_cap_id)}`}
                        className="flex items-baseline gap-2 text-xs hover:bg-white rounded px-1 py-0.5 -mx-1"
                      >
                        <span className="font-mono text-[10px] text-zen-teal shrink-0">
                          {s.sub_cap_id}
                        </span>
                        <span className="text-zen-dark-green truncate flex-1">
                          {s.sub_cap_name || '(no name)'}
                        </span>
                        {s.zennify_status && s.zennify_status.toLowerCase() !== 'active' && (
                          <span className="text-[9px] uppercase text-zen-muted-text bg-zen-separator/40 rounded px-1">
                            {s.zennify_status}
                          </span>
                        )}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
        {cat.l1s.length === 0 && (
          <li className="px-2 py-2 text-xs text-zen-muted-text italic">No L1 capabilities.</li>
        )}
      </ul>
    </article>
  );
}
