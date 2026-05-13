import { useQuery } from '@tanstack/react-query';
import { useSearchParams, Link } from 'react-router-dom';
import { apiGet, type SubcapDetail } from '@/lib/api';

type SubcapDetailV3 = SubcapDetail & {
  sow_signals?: {
    mention_count: number;
    client_count: number;
    mentions: Array<{ sow_id: string; sub_cap_id: string; method: string; excerpt: string; client_name?: string; status?: string; confidence: number }>;
  };
  story_signals?: {
    canonical_count: number;
    jira_count: number;
    canonical: Array<{ story_key: string; summary?: string; confidence_level?: string; composite_score?: number }>;
    jira: Array<{ story_key: string; summary?: string }>;
  };
};

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

  const { data, isLoading, error } = useQuery<SubcapDetailV3>({
    queryKey: ['subcap', id],
    queryFn: () => apiGet<SubcapDetailV3>(`/catalogue/subcaps/${encodeURIComponent(id || '')}`),
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

      {/* Completeness profile — at-a-glance counts of every link type
          (stories, L4 features, maturity descriptors, L3 platforms,
          use cases, themes, SOW mentions) bound to this subcap. Mirrors
          Sheet 18 (SubCap_Completeness_Profile) of the Pillar workbook. */}
      <Section title="Completeness profile">
        <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-7 gap-1.5">
          <Stat n={data.stories?.length || 0} label="Stories" />
          <Stat n={data.l4_features?.length || 0} label="L4 features" />
          <Stat
            n={['m1', 'm2', 'm3', 'm4', 'm5'].filter((k) => (m as Record<string, string | null>)[k]).length}
            label="M-levels"
            sub="of 5"
          />
          <Stat
            n={Array.from(
              new Set(
                (data.l4_features || []).flatMap((f) =>
                  ((f as Record<string, unknown>).l3_platform_id ? [(f as Record<string, string>).l3_platform_id] : []),
                ),
              ),
            ).length}
            label="L3 platforms"
          />
          <Stat n={data.use_cases?.length || 0} label="Use cases" />
          <Stat n={data.themes?.length || 0} label="Themes" />
          <Stat n={data.sow_signals?.mention_count || 0} label="SOW mentions" />
        </div>
      </Section>

      {s.description && (
        <Section title="Description">
          <p className="text-sm text-zen-dark-teal whitespace-pre-line">{s.description}</p>
        </Section>
      )}

      <Section title="Maturity ladder">
        {/* 5-card horizontal strip — ZDS 5-tier maturity bands (Foundational →
            Transformational). Active card = descriptor populated. */}
        <div className="grid grid-cols-1 sm:grid-cols-5 gap-2">
          {MATURITY_LEVELS.map((lvl, i) => {
            const desc = (m as Record<string, string | null>)[lvl.key];
            const feat = (m as Record<string, string | null>)[lvl.features];
            const active = Boolean(desc);
            // ZDS canonical bg + circle from color_authority.md.
            const bands = [
              { bg: 'bg-zen-light-orange/40', accent: 'bg-zen-orange', label: 'Foundational' },
              { bg: 'bg-zen-purple-grey/40',  accent: 'bg-zen-dark-purple', label: 'Developing' },
              { bg: 'bg-zen-light-blue/30',   accent: 'bg-zen-blue', label: 'Established' },
              { bg: 'bg-zen-ice',             accent: 'bg-zen-light-teal', label: 'Advanced' },
              { bg: 'bg-zen-light-green/50',  accent: 'bg-zen-teal', label: 'Transformational' },
            ][i];
            return (
              <div
                key={lvl.key}
                className={[
                  'rounded-lg border p-3 min-h-[140px] flex flex-col',
                  active ? 'border-zen-separator shadow-sm' : 'border-zen-separator/50 opacity-60',
                  bands.bg,
                ].join(' ')}
              >
                <div className="flex items-center gap-2 mb-1.5">
                  <div className={`w-6 h-6 rounded-full text-white text-xs font-semibold flex items-center justify-center ${bands.accent}`}>
                    {i + 1}
                  </div>
                  <div className="text-[10px] uppercase tracking-wider font-semibold text-zen-dark-green">
                    {bands.label}
                  </div>
                </div>
                {desc ? (
                  <div className="text-xs text-zen-dark-green whitespace-pre-line">{desc}</div>
                ) : (
                  <em className="text-xs text-zen-muted-text">No descriptor captured</em>
                )}
                {feat && (
                  <div className="text-[11px] text-zen-text-gray mt-2 whitespace-pre-line border-t border-zen-separator/40 pt-1.5">
                    {feat}
                  </div>
                )}
              </div>
            );
          })}
        </div>
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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Section title={`SOW signals (${data.sow_signals?.mention_count ?? 0} mentions across ${data.sow_signals?.client_count ?? 0} clients)`}>
          {(data.sow_signals?.mention_count ?? 0) === 0 ? (
            <Empty />
          ) : (
            <ul className="space-y-2 max-h-72 overflow-auto">
              {data.sow_signals!.mentions.slice(0, 20).map((m) => (
                <li key={m.sow_id + m.method} className="text-xs">
                  <div className="flex items-center gap-2 text-zen-dark-green">
                    <span className="font-semibold">{m.client_name}</span>
                    {m.status && (
                      <span className="text-[10px] uppercase rounded px-1 bg-zen-light-green/60 text-zen-dark-teal">
                        {m.status}
                      </span>
                    )}
                    <span className="text-[10px] text-zen-dark-teal/60">[{m.method} · {m.confidence.toFixed(0)}]</span>
                  </div>
                  <div className="text-zen-dark-teal italic mt-0.5">“{m.excerpt}”</div>
                </li>
              ))}
            </ul>
          )}
          <div className="mt-2 text-[10px] text-zen-dark-teal/60">
            <Link to={`/trace?id=${encodeURIComponent(id!)}`} className="underline hover:text-zen-dark-green">
              View full Project–Subcap Trace →
            </Link>
          </div>
        </Section>

        <Section title={`Story signals (canonical ${data.story_signals?.canonical_count ?? 0} · Jira ${data.story_signals?.jira_count ?? 0})`}>
          {(data.story_signals?.canonical_count ?? 0) === 0 && (data.story_signals?.jira_count ?? 0) === 0 ? (
            <Empty />
          ) : (
            <ul className="space-y-1 max-h-72 overflow-auto">
              {data.story_signals!.canonical.map((s) => (
                <li key={s.story_key} className="text-xs">
                  <span className="font-mono text-[10px] text-zen-dark-teal/60 mr-1">{s.story_key}</span>
                  {s.confidence_level && (
                    <span className="text-[9px] uppercase rounded px-1 bg-zen-teal/30 text-zen-dark-green mr-1">
                      {s.confidence_level}
                    </span>
                  )}
                  <span className="text-zen-dark-teal">{s.summary?.slice(0, 160)}</span>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>

      <Section title="Coming soon">
        <div className="text-xs text-zen-text-gray grid grid-cols-1 md:grid-cols-2 gap-1">
          <div>• Public evidence + Evidence Reliability Score</div>
          <div>• Benchmark distribution + adversary verdict</div>
          <div>• Lifecycle decay scoring</div>
          <div>• Vendor competitive intelligence</div>
          <div>• Reasoning-chain drilldown</div>
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

function Stat({ n, label, sub }: { n: number; label: string; sub?: string }) {
  return (
    <div className="bg-zen-ice/60 rounded p-2 text-center">
      <div className={`text-lg font-semibold ${n > 0 ? 'text-zen-teal' : 'text-zen-muted-text'}`}>
        {n}
      </div>
      <div className="text-[10px] uppercase tracking-wider text-zen-text-gray">{label}</div>
      {sub && <div className="text-[9px] text-zen-muted-text">{sub}</div>}
    </div>
  );
}
