import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { apiGet, type CentralityRow, type GraphElements, type GraphSummary } from '@/lib/api';
import KnowledgeGraphView from '@/components/KnowledgeGraphView';

const ALL_KINDS = [
  'Pillar',
  'Category',
  'L1_Capability',
  'Subcap',
  'L3_Platform',
  'L4_Feature',
  'UseCase',
  'UC_Tag',
  'Theme',
  'MaturityDescriptor',
  'Subvertical',
  'Cluster',
  'VC_Stage',
  'Persona',
];

const DEFAULT_KINDS = ['Pillar', 'Category', 'L1_Capability', 'Subcap', 'L3_Platform'];

export default function KnowledgeGraph() {
  const navigate = useNavigate();
  const [kinds, setKinds] = useState<Set<string>>(new Set(DEFAULT_KINDS));
  const [maxNodes, setMaxNodes] = useState(500);
  const [centralityMetric, setCentralityMetric] = useState<'degree' | 'pagerank' | 'betweenness'>('degree');

  const kindsParam = useMemo(() => Array.from(kinds).join(','), [kinds]);

  const { data: summary } = useQuery<GraphSummary>({
    queryKey: ['kg-summary'],
    queryFn: () => apiGet<GraphSummary>('/graph/summary'),
  });

  const { data: elements, isLoading } = useQuery<GraphElements>({
    queryKey: ['kg-elements', kindsParam, maxNodes],
    queryFn: () => apiGet<GraphElements>(`/graph/elements?kinds=${kindsParam}&max_nodes=${maxNodes}`),
    enabled: kinds.size > 0,
  });

  const { data: top } = useQuery<CentralityRow[]>({
    queryKey: ['kg-centrality', centralityMetric],
    queryFn: () => apiGet<CentralityRow[]>(`/graph/centrality?metric=${centralityMetric}&limit=15`),
  });

  const toggle = (k: string) =>
    setKinds((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });

  const onSelect = (nodeId: string) => {
    if (nodeId.startsWith('Subcap:')) {
      navigate(`/subcap?id=${encodeURIComponent(nodeId.slice('Subcap:'.length))}`);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-zen-dark-green">Knowledge Graph</h1>
          <p className="text-sm text-zen-dark-teal/80 max-w-3xl">
            Interconnections across the catalogue — Pillars, Categories, L1 Capabilities,
            Subcaps, Platforms, Use Cases, Themes, plus SOWs, vendors, news, filings, and
            benchmarks as those streams populate.
          </p>
        </div>
        <a
          href="/api/graph/export.yaml"
          className="text-xs bg-zen-teal hover:bg-zen-dark-teal text-white font-medium px-3 py-1.5 rounded transition-colors duration-200 whitespace-nowrap"
          download="knowledge-graph.yaml"
        >
          Download YAML
        </a>
      </div>

      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-xs">
          <Stat label="Snapshot" value={summary.snapshot_id} mono />
          <Stat label="Nodes" value={summary.nodes_total.toLocaleString()} />
          <Stat label="Edges" value={summary.edges_total.toLocaleString()} />
          <Stat label="Node kinds" value={Object.keys(summary.nodes_by_type).length.toString()} />
          <Stat label="Edge kinds" value={Object.keys(summary.edges_by_type).length.toString()} />
        </div>
      )}

      <div className="bg-white rounded-lg border border-zen-light-green/40 p-3">
        <div className="text-xs font-semibold text-zen-dark-green uppercase tracking-wider mb-2">
          Node-type filter (max-render: {maxNodes})
        </div>
        <div className="flex flex-wrap gap-1.5">
          {ALL_KINDS.map((k) => (
            <button
              key={k}
              onClick={() => toggle(k)}
              className={`text-[10px] uppercase tracking-wider rounded px-2 py-0.5 ${
                kinds.has(k)
                  ? 'bg-zen-dark-green text-white'
                  : 'bg-zen-light-green/40 text-zen-dark-teal/70 hover:bg-zen-light-green/70'
              }`}
            >
              {k}
              {summary?.nodes_by_type[k] ? <span className="ml-1 opacity-70">{summary.nodes_by_type[k]}</span> : null}
            </button>
          ))}
        </div>
        <div className="mt-2 flex items-center gap-2 text-xs">
          <label>Max nodes</label>
          <input
            type="range"
            min={50}
            max={2000}
            step={50}
            value={maxNodes}
            onChange={(e) => setMaxNodes(Number(e.target.value))}
          />
          <span className="font-mono text-zen-dark-teal">{maxNodes}</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <div className="lg:col-span-2">
          {isLoading && <div className="text-xs text-zen-dark-teal/60">Building layout…</div>}
          {elements && (
            <>
              {elements.truncated && (
                <div className="text-[10px] text-zen-orange mb-1">
                  Render truncated: more nodes match than max-render setting allows.
                </div>
              )}
              <KnowledgeGraphView elements={elements} onSelect={onSelect} />
            </>
          )}
        </div>

        <div className="bg-white rounded-lg border border-zen-light-green/40 p-3">
          <div className="text-xs font-semibold text-zen-dark-green uppercase tracking-wider mb-2">
            Centrality (top 15)
          </div>
          <div className="flex gap-1 mb-2 text-[10px]">
            {(['degree', 'pagerank', 'betweenness'] as const).map((m) => (
              <button
                key={m}
                onClick={() => setCentralityMetric(m)}
                className={`rounded px-1.5 py-0.5 ${
                  centralityMetric === m ? 'bg-zen-dark-green text-white' : 'bg-zen-light-green/40 text-zen-dark-teal'
                }`}
              >
                {m}
              </button>
            ))}
          </div>
          {!top && <div className="text-xs text-zen-dark-teal/60">Computing…</div>}
          {top && (
            <ul className="text-xs space-y-1 max-h-[480px] overflow-auto">
              {top.map((row) => (
                <li key={row.id} className="flex items-center justify-between gap-2">
                  <button
                    type="button"
                    className="text-left flex-1 min-w-0 truncate text-zen-dark-teal hover:text-zen-dark-green"
                    onClick={() => onSelect(row.id)}
                    title={row.id}
                  >
                    <span className="text-[9px] uppercase tracking-wider text-zen-dark-teal/60 mr-1">
                      {row.kind}
                    </span>
                    {row.label}
                  </button>
                  <span className="font-mono text-[10px] text-zen-dark-teal/70">
                    {row.score < 0.01 ? row.score.toExponential(1) : row.score.toFixed(2)}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-3 text-[10px] text-zen-text-gray">
            Communities (Louvain), shortest-path, and impact-analysis are exposed at{' '}
            <span className="font-mono">/api/graph/*</span>.
          </div>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="bg-white rounded-lg border border-zen-light-green/40 p-2">
      <div className="text-[10px] uppercase tracking-wider text-zen-dark-teal/60">{label}</div>
      <div className={`text-zen-dark-green ${mono ? 'font-mono text-xs' : 'text-sm font-semibold'}`}>{value}</div>
    </div>
  );
}
