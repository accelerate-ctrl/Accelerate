import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { apiGet, type SubcapDetail } from '@/lib/api';

const MATURITY_LEVELS = [
  { key: 'm1', label: 'M1 — Foundational', features: 'm1_features' },
  { key: 'm2', label: 'M2 — Developing', features: 'm2_features' },
  { key: 'm3', label: 'M3 — Established / AI-Assisted', features: 'm3_features' },
  { key: 'm4', label: 'M4 — Advanced Hybrid Agentic', features: 'm4_features' },
  { key: 'm5', label: 'M5 — Transformational Headless360', features: 'm5_features' },
] as const;

export default function SubcapDeepDive() {
  const [params] = useSearchParams();
  const id = params.get('id');

  const { data, isLoading, error } = useQuery<SubcapDetail>({
    queryKey: ['subcap', id],
    queryFn: () => apiGet<SubcapDetail>(`/catalogue/subcaps/${encodeURIComponent(id || '')}`),
    enabled: !!id,
  });

  if (!id) {
    return (
      <div className="bg-white rounded-lg border border-zen-light-green/40 p-6">
        <h1 className="text-xl font-semibold text-zen-dark-green">Subcap Deep Dive</h1>
        <p className="text-sm text-zen-dark-teal/70 mt-2">
          Select a subcap from the Capability Explorer to see its full detail.
        </p>
      </div>
    );
  }

  if (isLoading) return <div className="text-xs text-zen-dark-teal/60">Loading {id}…</div>;
  if (error || !data) return <div className="text-xs text-zen-orange">Subcap not found: {id}</div>;

  const s = data.subcap;
  const m = data.maturity || {};

  return (
    <div className="space-y-4">
      <div>
        <div className="text-xs font-mono text-zen-dark-teal/70">{s.sub_cap_id}</div>
        <h1 className="text-2xl font-semibold text-zen-dark-green">{s.sub_cap_name}</h1>
        <div className="text-xs text-zen-dark-teal mt-1 flex flex-wrap gap-2 items-center">
          <span className="bg-zen-dark-green text-white rounded px-1.5 py-0.5">{s.pillar_id}</span>
          <span>{s.category_id}</span>
          <span>·</span>
          <span>{s.l1_capability}</span>
          {s.tier && (
            <span className="bg-zen-light-green/60 text-zen-dark-teal rounded px-1.5 py-0.5">{s.tier}</span>
          )}
          {s.zennify_status && (
            <span className="bg-zen-teal/30 text-zen-dark-green rounded px-1.5 py-0.5">{s.zennify_status}</span>
          )}
        </div>
      </div>

      {s.description && (
        <Section title="Description">
          <p className="text-sm text-zen-dark-teal whitespace-pre-line">{s.description}</p>
        </Section>
      )}

      <Section title="Maturity (M1 → M5)">
        <ul className="space-y-2">
          {MATURITY_LEVELS.map((lvl) => (
            <li key={lvl.key} className="border border-zen-light-green/40 rounded p-2">
              <div className="text-xs font-semibold text-zen-dark-green">{lvl.label}</div>
              <div className="text-sm text-zen-dark-teal mt-0.5 whitespace-pre-line">
                {(m as Record<string, string | null>)[lvl.key] || <em className="text-zen-dark-teal/50">(no descriptor)</em>}
              </div>
              {(m as Record<string, string | null>)[lvl.features] && (
                <div className="text-xs text-zen-dark-teal/80 mt-1 whitespace-pre-line">
                  {(m as Record<string, string | null>)[lvl.features]}
                </div>
              )}
            </li>
          ))}
        </ul>
      </Section>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Section title={`L4 Features (${data.l4_features.length})`}>
          {data.l4_features.length === 0 ? (
            <Empty />
          ) : (
            <ul className="space-y-1.5">
              {data.l4_features.slice(0, 25).map((f, i) => (
                <li key={i} className="text-xs">
                  <div className="font-medium text-zen-dark-green">{(f as Record<string, string>).feature_name}</div>
                  <div className="text-zen-dark-teal/70">
                    {(f as Record<string, string>).vendor} · {(f as Record<string, string>).feature_type}
                  </div>
                </li>
              ))}
              {data.l4_features.length > 25 && (
                <li className="text-[10px] text-zen-dark-teal/60">… and {data.l4_features.length - 25} more</li>
              )}
            </ul>
          )}
        </Section>

        <Section title={`Use Cases (${data.use_cases.length})`}>
          {data.use_cases.length === 0 ? (
            <Empty />
          ) : (
            <ul className="space-y-1">
              {data.use_cases.map((uc, i) => (
                <li key={i} className="text-xs text-zen-dark-teal">
                  <span className="font-mono text-[10px] text-zen-dark-teal/60 mr-1">
                    {(uc as Record<string, string>).use_case_id}
                  </span>
                  <span className="bg-zen-light-green/40 text-zen-dark-green rounded px-1 py-px text-[9px] mr-1">
                    {(uc as Record<string, string>).label}
                  </span>
                  {(uc as Record<string, string>).description}
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title={`Themes (${data.themes.length})`}>
          {data.themes.length === 0 ? (
            <Empty />
          ) : (
            <ul className="space-y-1 text-xs text-zen-dark-teal">
              {data.themes.map((t, i) => (
                <li key={i}>
                  <span className="bg-zen-dark-green text-white rounded px-1.5 py-0.5 text-[10px] mr-1">
                    {(t as Record<string, string>).theme}
                  </span>
                  {(t as Record<string, string>).rationale}
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title={`Stories (${data.stories.length})`}>
          {data.stories.length === 0 ? (
            <Empty />
          ) : (
            <ul className="space-y-1 text-xs text-zen-dark-teal">
              {data.stories.slice(0, 20).map((st, i) => (
                <li key={i}>
                  <span className="font-mono text-[10px] text-zen-dark-teal/60 mr-1">
                    {(st as Record<string, string>).story_key}
                  </span>
                  {(st as Record<string, string>).summary}
                </li>
              ))}
              {data.stories.length > 20 && (
                <li className="text-[10px] text-zen-dark-teal/60">… and {data.stories.length - 20} more</li>
              )}
            </ul>
          )}
        </Section>
      </div>

      <Section title="Pending in later batches">
        <div className="text-xs text-zen-dark-teal/70 grid grid-cols-1 md:grid-cols-2 gap-1">
          <div>• SOW signals (Batch 3)</div>
          <div>• Public evidence + ERS (Batch 4)</div>
          <div>• Benchmarks + adversary verdict (Batch 5)</div>
          <div>• Lifecycle scoring (Batch 6)</div>
          <div>• Vendor competitive intel (Batch 6)</div>
          <div>• Reasoning chain (Batch 4)</div>
        </div>
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-lg shadow-sm border border-zen-light-green/40 p-3">
      <h2 className="text-xs font-semibold text-zen-dark-green uppercase tracking-wider mb-2">{title}</h2>
      {children}
    </div>
  );
}

function Empty() {
  return <div className="text-xs text-zen-dark-teal/50 italic">none</div>;
}
