import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, Minus, Plus } from 'lucide-react';
import { apiGet, type CatalogueVersion, type Diff } from '@/lib/api';

export default function DiffViewer() {
  const [params, setParams] = useSearchParams();
  const { data: versions } = useQuery<CatalogueVersion[]>({
    queryKey: ['versions'],
    queryFn: () => apiGet<CatalogueVersion[]>('/versions'),
  });

  const [a, setA] = useState(params.get('a') || '');
  const [b, setB] = useState(params.get('b') || '');

  // If a/b not set, default to most recent two
  useEffect(() => {
    if (!a && !b && versions && versions.length >= 2) {
      const next = { a: versions[1].version_id, b: versions[0].version_id };
      setA(next.a);
      setB(next.b);
      setParams({ a: next.a, b: next.b });
    }
  }, [versions, a, b, setParams]);

  const { data: diff } = useQuery<Diff>({
    queryKey: ['diff', a, b],
    queryFn: () => apiGet<Diff>(`/diffs/${a}/${b}`),
    enabled: !!a && !!b,
  });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-zen-dark-green">Diff Viewer</h1>
        <p className="text-sm text-zen-dark-teal/80">Field-level differences between two catalogue versions.</p>
      </div>

      <div className="bg-white rounded-lg shadow-sm border border-zen-light-green/40 p-3 flex items-center gap-3 flex-wrap">
        <Picker label="A" value={a} onChange={(v) => { setA(v); setParams({ a: v, b }); }} versions={versions || []} />
        <ArrowRight size={16} className="text-zen-dark-teal" />
        <Picker label="B" value={b} onChange={(v) => { setB(v); setParams({ a, b: v }); }} versions={versions || []} />
      </div>

      {diff && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          <Card title={`Added subcaps (${diff.added_subcaps.length})`} icon={<Plus size={14} className="text-zen-teal" />}>
            <List items={diff.added_subcaps} />
          </Card>
          <Card title={`Removed subcaps (${diff.removed_subcaps.length})`} icon={<Minus size={14} className="text-zen-orange" />}>
            <List items={diff.removed_subcaps} />
          </Card>
          <Card title={`Modified subcaps (${diff.modified_subcaps.length})`} icon={null}>
            {diff.modified_subcaps.length === 0 ? (
              <Empty />
            ) : (
              <ul className="space-y-2 max-h-72 overflow-auto">
                {diff.modified_subcaps.slice(0, 50).map((m) => (
                  <li key={m.sub_cap_id} className="text-xs">
                    <div className="font-mono text-zen-dark-green">{m.sub_cap_id}</div>
                    <ul className="pl-2 mt-0.5 space-y-0.5">
                      {Object.entries(m.fields).slice(0, 4).map(([f, ab]) => (
                        <li key={f}>
                          <span className="text-zen-dark-teal/70">{f}</span>:{' '}
                          <span className="line-through text-zen-orange/80">{String(ab.a).slice(0, 40)}</span>{' '}
                          → <span className="text-zen-teal">{String(ab.b).slice(0, 40)}</span>
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card title="Pillar count delta" icon={null}>
            <ul className="text-xs space-y-1">
              {Object.entries(diff.pillar_count_deltas).map(([k, n]) => (
                <li key={k}>
                  <span className="font-mono text-zen-dark-green mr-1">{k}</span>
                  <span className={n > 0 ? 'text-zen-teal' : n < 0 ? 'text-zen-orange' : 'text-zen-dark-teal/60'}>
                    {n > 0 ? '+' : ''}
                    {n}
                  </span>
                </li>
              ))}
            </ul>
          </Card>
          <Card title={`Categories Δ`} icon={null}>
            <div className="text-xs text-zen-dark-teal">
              <div className="text-zen-teal">+ {diff.added_categories.join(', ') || 'none'}</div>
              <div className="text-zen-orange mt-1">− {diff.removed_categories.join(', ') || 'none'}</div>
            </div>
          </Card>
          <Card title="Narrative" icon={null}>
            <div className="text-xs text-zen-text-gray italic">
              AI narrative populates once the LLM router is reachable from this revision.
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

function Picker({
  label,
  value,
  onChange,
  versions,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  versions: CatalogueVersion[];
}) {
  return (
    <div className="flex items-center gap-1 text-sm">
      <span className="text-zen-dark-teal/70">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="border border-zen-light-green rounded px-2 py-1 text-xs"
      >
        <option value="">— select —</option>
        {versions.map((v) => (
          <option key={v.version_id} value={v.version_id}>
            {v.version_id} {v.label ? `· ${v.label}` : ''}
          </option>
        ))}
      </select>
    </div>
  );
}

function Card({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-lg shadow-sm border border-zen-light-green/40 p-3">
      <h2 className="text-xs font-semibold text-zen-dark-green uppercase tracking-wider mb-2 flex items-center gap-1">
        {icon} {title}
      </h2>
      {children}
    </div>
  );
}

function List({ items }: { items: string[] }) {
  if (items.length === 0) return <Empty />;
  return (
    <ul className="text-xs font-mono text-zen-dark-teal max-h-72 overflow-auto space-y-0.5">
      {items.slice(0, 50).map((s) => (
        <li key={s}>{s}</li>
      ))}
      {items.length > 50 && <li className="text-zen-dark-teal/50">… and {items.length - 50} more</li>}
    </ul>
  );
}

function Empty() {
  return <div className="text-xs text-zen-dark-teal/50 italic">none</div>;
}
