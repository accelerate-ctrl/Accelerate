import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { apiGet, type SubcapDetail } from '@/lib/api';
import CascadePreviewModal from '@/components/CascadePreviewModal';

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
  const queryClient = useQueryClient();
  const [cascadeOpen, setCascadeOpen] = useState<null | 'Inactive' | 'Active'>(null);

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
          {/* Toggle action — opens the cascade preview modal (J4). */}
          <button
            type="button"
            onClick={() =>
              setCascadeOpen(s.zennify_status === 'Inactive' ? 'Active' : 'Inactive')
            }
            className="ml-auto text-[11px] bg-zen-ice text-zen-dark-green border border-zen-separator rounded px-2 py-0.5 hover:bg-zen-light-green/40"
            title="Open the cascade preview before toggling this subcap"
          >
            Toggle status…
          </button>
        </div>
      </div>

      {cascadeOpen && id && (
        <CascadePreviewModal
          subCapId={id}
          toStatus={cascadeOpen}
          onCancel={() => setCascadeOpen(null)}
          onApplied={() => {
            setCascadeOpen(null);
            // Refresh the deep-dive payload so the new status is visible.
            queryClient.invalidateQueries({ queryKey: ['subcap', id] });
          }}
        />
      )}

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
        {data.completeness?.total_score !== undefined && (
          <div className="mt-3 flex items-center gap-2 text-xs">
            <span className="bg-zen-teal/20 text-zen-dark-green rounded px-2 py-1 font-medium">
              Workbook score: {data.completeness.total_score}/8
            </span>
            {data.completeness.core_score !== undefined && (
              <span className="text-fg-soft">
                core {data.completeness.core_score}/5 · extended {data.completeness.extended_score ?? 0}/3
              </span>
            )}
          </div>
        )}
      </Section>

      {/* v7.0: Productized offerings that address this subcap (tab 12) */}
      {data.offerings && data.offerings.length > 0 && (
        <Section title={`Productized offerings (${data.offerings.length})`}>
          <ul className="space-y-2">
            {data.offerings.map((o) => (
              <li key={`${o.offering_id}-${o.sub_cap_id}`} className="border border-zen-separator rounded p-2">
                <div className="flex items-center gap-2 text-sm font-medium text-zen-dark-green">
                  <span className="font-mono text-[11px] bg-zen-ice rounded px-1.5 py-0.5">
                    {o.offering_id}
                  </span>
                  <span>{o.offering_name}</span>
                  {o.zennify_effective_status && (
                    <span className="ml-auto text-[10px] bg-zen-light-green/40 text-zen-dark-teal rounded px-1.5 py-0.5">
                      {o.zennify_effective_status}
                    </span>
                  )}
                </div>
                {o.mapping_rationale && (
                  <p className="mt-1 text-xs text-zen-dark-teal/80 line-clamp-3">{o.mapping_rationale}</p>
                )}
                {o.maturity_lift && (
                  <p className="mt-1 text-[11px] text-zen-text-gray italic">{o.maturity_lift}</p>
                )}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* v7.0: Data products that ground this subcap (tab 13) */}
      {data.data_products && data.data_products.length > 0 && (
        <Section title={`Data products (${data.data_products.length})`}>
          <ul className="space-y-2">
            {data.data_products.map((dp) => (
              <li key={`${dp.module_id}-${dp.sub_cap_id}`} className="border border-zen-separator rounded p-2">
                <div className="flex items-center gap-2 text-sm font-medium text-zen-dark-green">
                  <span className="font-mono text-[11px] bg-zen-ice rounded px-1.5 py-0.5">{dp.module_id}</span>
                  <span>{dp.module_name}</span>
                </div>
                {dp.mapping_rationale && (
                  <p className="mt-1 text-xs text-zen-dark-teal/80 line-clamp-3">{dp.mapping_rationale}</p>
                )}
                {dp.maturity_lift && (
                  <p className="mt-1 text-[11px] text-zen-text-gray italic">{dp.maturity_lift}</p>
                )}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* Phase 2.1 — News items touching this subcap, with per-subcap
          magnitude chips. Surfaces the new affected_subcaps payload
          from the news impact classifier. */}
      {data.affected_news && data.affected_news.length > 0 && (
        <Section title={`News impact (${data.affected_news.length})`}>
          <ul className="space-y-2">
            {data.affected_news.map((n) => (
              <li key={n.news_id} className="border border-zen-separator rounded p-2">
                <div className="flex items-start gap-2">
                  <span
                    className={`text-[10px] uppercase tracking-wider rounded px-1.5 py-0.5 shrink-0 ${
                      n.magnitude === 'HIGH'
                        ? 'bg-zen-orange text-white'
                        : n.magnitude === 'MEDIUM'
                        ? 'bg-zen-light-orange text-zen-dark-green'
                        : 'bg-zen-light-green/60 text-zen-dark-green'
                    }`}
                  >
                    {n.magnitude}
                  </span>
                  <div className="flex-1 min-w-0">
                    {n.url ? (
                      <a
                        href={n.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm text-zen-dark-green font-medium hover:underline"
                      >
                        {n.title}
                      </a>
                    ) : (
                      <span className="text-sm text-zen-dark-green font-medium">{n.title}</span>
                    )}
                    <div className="text-[11px] text-zen-text-gray mt-0.5">
                      {n.source}
                      {n.published_at && ` · ${new Date(n.published_at).toLocaleDateString()}`}
                    </div>
                    {n.rationale && (
                      <p className="text-xs text-zen-dark-teal/80 mt-1 italic">{n.rationale}</p>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* v7.0: Cross-pillar coverage breakdown (tab 16) */}
      {data.cross_pillar_coverage && data.cross_pillar_coverage.total_cross_pillar_stories ? (
        <Section title="Cross-pillar coverage">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5">
            <Stat n={data.cross_pillar_coverage.total_cross_pillar_stories || 0} label="Total stories" />
            <Stat n={data.cross_pillar_coverage.p2_stories || 0} label="From P2" />
            <Stat n={data.cross_pillar_coverage.p3_stories || 0} label="From P3" />
            <Stat n={data.cross_pillar_coverage.p4_stories || 0} label="From P4" />
          </div>
          {data.cross_pillar_coverage.themes_contributing && data.cross_pillar_coverage.themes_contributing.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {data.cross_pillar_coverage.themes_contributing.map((t) => (
                <span key={t} className="text-[10px] bg-zen-purple-grey/40 text-zen-dark-teal rounded px-1.5 py-0.5">
                  {t}
                </span>
              ))}
            </div>
          )}
        </Section>
      ) : null}

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

      {/* Phase 3.4 — Personas section. The persona refs are parsed
          from v7.0 cells with paren-aware tokenization (Phase 1.1) so
          each chip can show the canonical name + family + role. */}
      {((s.persona_refs && s.persona_refs.length > 0) || (s.personas && s.personas.length > 0)) && (
        <Section title={`Personas (${(s.persona_refs?.length || s.personas?.length || 0)})`}>
          <div className="flex flex-wrap gap-1.5">
            {s.persona_refs && s.persona_refs.length > 0
              ? s.persona_refs.map((p, i) => (
                  <div
                    key={`${p.canonical_name}-${i}`}
                    className="text-xs bg-zen-ice text-zen-dark-green rounded px-2 py-1"
                    title={p.role_description || p.canonical_name}
                  >
                    <span className="font-medium">{p.canonical_name}</span>
                    {p.family && (
                      <span className="ml-1 text-[10px] text-zen-text-gray uppercase">{p.family}</span>
                    )}
                  </div>
                ))
              : (s.personas || []).map((name, i) => (
                  <span
                    key={`${name}-${i}`}
                    className="text-xs bg-zen-ice text-zen-dark-green rounded px-2 py-1"
                  >
                    {name}
                  </span>
                ))}
          </div>
        </Section>
      )}

      {/* Phase 3.4 — Lifecycle history. Newest transitions first.
          Uses the lifecycle_transitions append-only log (Phase 1.1
          F11 vocabulary fix). */}
      {data.lifecycle_history && data.lifecycle_history.length > 0 && (
        <Section title={`Lifecycle history (${data.lifecycle_history.length})`}>
          <ul className="space-y-1.5">
            {data.lifecycle_history.slice(0, 8).map((t, i) => (
              <li
                key={t.transition_id || i}
                className="text-xs text-zen-dark-teal flex items-center gap-2"
              >
                <span className="font-mono text-[10px] text-zen-text-gray min-w-[8ch]">
                  {t.transitioned_at?.slice(0, 10) || t.recorded_at?.slice(0, 10) || '—'}
                </span>
                <span className="text-zen-text-gray">
                  {t.from_state || '—'}
                </span>
                <span className="text-zen-teal">→</span>
                <span className="font-medium text-zen-dark-green">{t.to_state || '—'}</span>
                {t.reason && <span className="text-[11px] text-zen-text-gray ml-2 italic">"{t.reason}"</span>}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* Phase 3.4 — Vendor activity. vendor_events whose source news
          item AFFECTS this subcap. */}
      {data.vendor_activity && data.vendor_activity.length > 0 && (
        <Section title={`Vendor activity (${data.vendor_activity.length})`}>
          <ul className="space-y-1.5">
            {data.vendor_activity.slice(0, 8).map((e) => (
              <li key={e.event_id} className="text-xs text-zen-dark-teal flex items-start gap-2">
                <span className="font-mono text-[10px] text-zen-text-gray min-w-[8ch]">
                  {e.published_at?.slice(0, 10) || '—'}
                </span>
                <span className="bg-zen-light-green/40 text-zen-dark-teal rounded px-1.5 py-0.5 text-[10px]">
                  {e.vendor_name || e.vendor_id}
                </span>
                <span className="flex-1">
                  {e.url ? (
                    <a href={e.url} target="_blank" rel="noopener noreferrer" className="hover:underline text-zen-dark-green">
                      {e.title}
                    </a>
                  ) : (
                    e.title
                  )}
                </span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* Phase 3.4 — Recent reasoning chains. Threaded across the
          trust surface so the user can see what AI work has run
          against this subcap. */}
      {data.recent_chains && data.recent_chains.length > 0 && (
        <Section title={`Recent reasoning (${data.recent_chains.length})`}>
          <ul className="space-y-1">
            {data.recent_chains.slice(0, 8).map((c) => (
              <li key={c.chain_id} className="text-xs flex items-center gap-2">
                <span
                  className={`text-[10px] uppercase tracking-wider rounded px-1.5 py-0.5 ${
                    c.overall === 'pass'
                      ? 'bg-zen-light-green/60 text-zen-dark-green'
                      : c.overall === 'fail'
                      ? 'bg-zen-orange text-white'
                      : 'bg-zen-light-orange text-zen-dark-green'
                  }`}
                >
                  {c.overall || 'n/a'}
                </span>
                <span className="font-mono text-[10px] text-zen-text-gray">{c.operation}</span>
                <Link
                  to={`/reasoning?id=${encodeURIComponent(c.chain_id)}`}
                  className="text-zen-teal hover:text-zen-dark-teal underline truncate"
                >
                  {c.chain_id}
                </Link>
                {typeof c.total_cost_usd === 'number' && c.total_cost_usd > 0 && (
                  <span className="text-[10px] text-zen-text-gray ml-auto">
                    ${c.total_cost_usd.toFixed(4)}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* Phase 3.4 — AI Audit button (HIGH-tier ad-hoc run).
          Surfaces the cost disclosure inline per J3 / J6 contract. */}
      <Section title="Run AI audit">
        <div className="text-xs text-zen-text-gray mb-2">
          Triggers a HIGH-tier consultant-loop pass over this subcap (~$0.05–0.20).
          Produces a fresh reasoning chain you can review on the Reasoning
          Chain Viewer.
        </div>
        <button
          type="button"
          onClick={() => {
            window.location.href = `/reasoning?run=true&sub_cap_id=${encodeURIComponent(id || '')}`;
          }}
          className="text-xs bg-zen-teal text-white rounded px-3 py-1.5 hover:bg-zen-dark-teal"
        >
          Run HIGH-tier audit →
        </button>
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
