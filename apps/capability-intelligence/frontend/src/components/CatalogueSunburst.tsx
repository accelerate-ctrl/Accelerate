// Sunburst built on d3-hierarchy partition. Pillars (inner) → Categories →
// L1 → Subcaps (outer). Click drills the global filter; double-click jumps to
// the Subcap Deep Dive page.
import { useMemo, useRef } from 'react';
import { hierarchy, partition, type HierarchyRectangularNode } from 'd3-hierarchy';
import { useNavigate } from 'react-router-dom';
import type { Tree } from '@/lib/api';
import { useFilters } from '@/store/filters';

const PILLAR_COLORS: Record<string, string> = {
  P1: '#1c4a4d',
  P2: '#185f60',
  P3: '#27bbaf',
  P4: '#62d7b8',
};

type SunburstNode = {
  name: string;
  kind: 'root' | 'pillar' | 'category' | 'l1' | 'subcap';
  id?: string;
  pillar_id?: string;
  category_id?: string;
  sub_cap_id?: string;
  value?: number;
  children?: SunburstNode[];
};

function buildHierarchy(tree: Tree): SunburstNode {
  return {
    name: 'Catalogue',
    kind: 'root',
    children: tree.pillars.map((p) => ({
      name: p.name,
      kind: 'pillar',
      id: p.pillar_id,
      pillar_id: p.pillar_id,
      children: p.categories.map((c) => ({
        name: c.name,
        kind: 'category',
        id: c.category_id,
        pillar_id: p.pillar_id,
        category_id: c.category_id,
        children: c.l1.map((l1) => ({
          name: l1.name,
          kind: 'l1',
          pillar_id: p.pillar_id,
          category_id: c.category_id,
          children: l1.subcaps.map((s) => ({
            name: s.sub_cap_name,
            kind: 'subcap',
            id: s.sub_cap_id,
            pillar_id: p.pillar_id,
            category_id: c.category_id,
            sub_cap_id: s.sub_cap_id,
            value: 1,
          })),
        })),
      })),
    })),
  };
}

export default function CatalogueSunburst({ tree, size = 520 }: { tree: Tree; size?: number }) {
  const setPillar = useFilters((s) => s.setPillar);
  const setCategory = useFilters((s) => s.setCategory);
  const navigate = useNavigate();
  const tipRef = useRef<HTMLDivElement | null>(null);

  const arcs = useMemo<HierarchyRectangularNode<SunburstNode>[]>(() => {
    const root = hierarchy<SunburstNode>(buildHierarchy(tree)).sum((d) => d.value || 0);
    const layout = partition<SunburstNode>().size([2 * Math.PI, size / 2]);
    const partitioned = layout(root);
    return partitioned.descendants().filter((d) => d.depth > 0);
  }, [tree, size]);

  const cx = size / 2;
  const cy = size / 2;

  if (arcs.length === 0) {
    return (
      <div className="text-xs text-zen-dark-teal/70 p-4 bg-white rounded border border-zen-light-green/40">
        No catalogue data yet. Refresh a pillar from Mission Control to populate the chart.
      </div>
    );
  }

  return (
    <div className="relative inline-block">
      <svg width={size} height={size} role="img" aria-label="catalogue sunburst">
        <g transform={`translate(${cx},${cy})`}>
          {arcs.map((node, i) => {
            const d = arcPath(node.x0, node.x1, node.y0, node.y1);
            const fill = colorFor(node);
            const data = node.data;
            return (
              <path
                key={`${data.kind}-${data.id ?? data.name}-${i}`}
                d={d}
                fill={fill}
                fillOpacity={0.85}
                stroke="white"
                strokeWidth={1}
                style={{ cursor: 'pointer' }}
                onMouseEnter={(e) => {
                  if (tipRef.current) {
                    tipRef.current.textContent = `${data.kind}: ${data.name}`;
                    tipRef.current.style.opacity = '1';
                    tipRef.current.style.left = `${e.clientX + 10}px`;
                    tipRef.current.style.top = `${e.clientY + 10}px`;
                  }
                }}
                onMouseLeave={() => {
                  if (tipRef.current) tipRef.current.style.opacity = '0';
                }}
                onClick={() => {
                  if (data.kind === 'pillar' && data.pillar_id) setPillar(data.pillar_id);
                  if (data.kind === 'category' && data.category_id) {
                    setPillar(data.pillar_id || null);
                    setCategory(data.category_id);
                  }
                }}
                onDoubleClick={() => {
                  if (data.kind === 'subcap' && data.sub_cap_id) {
                    navigate(`/subcap?id=${encodeURIComponent(data.sub_cap_id)}`);
                  }
                }}
              />
            );
          })}
        </g>
      </svg>
      <div
        ref={tipRef}
        className="fixed pointer-events-none bg-zen-dark-green text-white text-xs px-2 py-1 rounded shadow opacity-0 transition-opacity z-50"
        style={{ left: 0, top: 0 }}
      />
    </div>
  );
}

function arcPath(x0: number, x1: number, y0: number, y1: number): string {
  const a0 = x0 - Math.PI / 2;
  const a1 = x1 - Math.PI / 2;
  const sx0 = Math.cos(a0) * y0;
  const sy0 = Math.sin(a0) * y0;
  const sx1 = Math.cos(a1) * y0;
  const sy1 = Math.sin(a1) * y0;
  const ex0 = Math.cos(a1) * y1;
  const ey0 = Math.sin(a1) * y1;
  const ex1 = Math.cos(a0) * y1;
  const ey1 = Math.sin(a0) * y1;
  const largeArc = x1 - x0 > Math.PI ? 1 : 0;
  return [
    `M${sx0},${sy0}`,
    `A${y0},${y0} 0 ${largeArc} 1 ${sx1},${sy1}`,
    `L${ex0},${ey0}`,
    `A${y1},${y1} 0 ${largeArc} 0 ${ex1},${ey1}`,
    'Z',
  ].join(' ');
}

function colorFor(node: HierarchyRectangularNode<SunburstNode>): string {
  const base = PILLAR_COLORS[node.data.pillar_id || ''] || '#27bbaf';
  // Lighten as we go outward
  const lighten = node.depth * 12;
  return shade(base, lighten);
}

function shade(hex: string, amount: number): string {
  const m = hex.replace('#', '');
  const num = parseInt(m, 16);
  const r = Math.min(255, ((num >> 16) & 0xff) + amount);
  const g = Math.min(255, ((num >> 8) & 0xff) + amount);
  const b = Math.min(255, (num & 0xff) + amount);
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, '0')}`;
}
