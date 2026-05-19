import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Building2,
  CheckCircle2,
  ExternalLink,
  Flame,
  Layers,
  RefreshCw,
  Sparkles,
  Wand2,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import {
  apiGet,
  apiPost,
  type VendorEvent,
  type VendorHeatmap,
  type VendorProfile,
} from '@/lib/api';

type Partner = {
  code: string;
  name: string;
  category: string;
  release_notes: string;
  rss_url: string | null;
  lookback_days: number;
};

type ReleaseFeature = {
  feature: string;
  summary: string;
  impact_class: 'new_feature' | 'enhancement' | 'deprecation' | 'bug_fix';
  category_hint?: string;
  mapped_l1?: string | null;
  score?: number;
  is_gap?: boolean;
};

type Release = {
  release_id: string;
  partner_code: string;
  partner_name: string;
  category: string;
  title: string;
  summary?: string;
  url?: string | null;
  published_at: string;
  source?: 'rss' | 'seed';
  features: ReleaseFeature[];
};

type CatalogueGap = {
  l1_capability: string;
  features: (ReleaseFeature & {
    partner_code: string;
    partner_name: string;
    release_id: string;
    release_url?: string | null;
    published_at: string;
    release_title: string;
  })[];
  partners: string[];
  count: number;
  last_seen: string;
};

const TABS = [
  { key: 'evidence', label: 'Subcap evidence' },
  { key: 'adoption', label: 'Adoption' },
  { key: 'releases', label: 'Releases' },
  { key: 'gaps', label: 'Catalogue gaps' },
] as const;
type TabKey = (typeof TABS)[number]['key'];

type SubcapEvidenceCell = {
  vendor_id: string;
  vendor_name?: string;
  sub_cap_id: string;
  magnitude: 'HIGH' | 'MEDIUM' | 'LOW';
  event_count: number;
  latest_event?: string | null;
};

type SubcapEvidenceHeatmap = {
  vendors: string[];
  subcaps: string[];
  cells: SubcapEvidenceCell[];
  total_events_joined: number;
};

const EVIDENCE_MAG_BG: Record<SubcapEvidenceCell['magnitude'], string> = {
  HIGH: 'bg-zen-orange text-white',
  MEDIUM: 'bg-zen-light-orange text-zen-dark-green',
  LOW: 'bg-zen-light-green/60 text-zen-dark-green',
};

const IMPACT_BADGE: Record<ReleaseFeature['impact_class'], string> = {
  new_feature: 'bg-zen-light-green/70 text-zen-dark-teal',
  enhancement: 'bg-zen-ice text-zen-dark-teal',
  deprecation: 'bg-zen-light-orange/70 text-zen-orange',
  bug_fix: 'bg-zen-purple-grey/40 text-zen-text-gray',
};

export default function VendorIntelligence() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<TabKey>('evidence');
  const [selectedPartner, setSelectedPartner] = useState<string | null>(null);
  const [selectedVendor, setSelectedVendor] = useState<string | null>(null);

  // Shared queries
  const { data: partners } = useQuery<Partner[]>({
    queryKey: ['partners'],
    queryFn: () => apiGet<Partner[]>('/vendor-intel/partners'),
  });

  const { data: releases } = useQuery<Release[]>({
    queryKey: ['partner-releases', selectedPartner],
    queryFn: () =>
      apiGet<Release[]>(
        '/vendor-intel/releases' +
          (selectedPartner ? `?partner_code=${encodeURIComponent(selectedPartner)}` : ''),
      ),
    enabled: tab === 'releases',
  });

  const { data: gaps } = useQuery<CatalogueGap[]>({
    queryKey: ['partner-gaps'],
    queryFn: () => apiGet<CatalogueGap[]>('/vendor-intel/catalogue-gaps'),
    enabled: tab === 'gaps',
  });

  const scan = useMutation({
    mutationFn: () =>
      apiPost<{
        run_id: string;
        entries_seen: number;
        features_extracted: number;
        suggestions_created: number;
        per_partner: Record<string, unknown>;
      }>('/vendor-intel/scan-releases', {}),
    onSettled: () => qc.invalidateQueries(),
  });

  // Vendor heatmap (Adoption tab — keeps existing pipeline)
  const { data: vendors } = useQuery<VendorProfile[]>({
    queryKey: ['vendors'],
    queryFn: () => apiGet<VendorProfile[]>('/vendor-intel/vendors'),
    enabled: tab === 'adoption',
  });
  const { data: heatmap } = useQuery<VendorHeatmap>({
    queryKey: ['vendor-heatmap'],
    queryFn: () => apiGet<VendorHeatmap>('/vendor-intel/heatmap'),
    enabled: tab === 'adoption',
  });
  const { data: events } = useQuery<VendorEvent[]>({
    queryKey: ['vendor-events', selectedVendor],
    queryFn: () =>
      apiGet<VendorEvent[]>(
        selectedVendor
          ? `/vendor-intel/events?vendor_id=${encodeURIComponent(selectedVendor)}`
          : '/vendor-intel/events',
      ),
    enabled: tab === 'adoption',
  });

  // Phase 2.3 — evidence-driven vendor × subcap heatmap.
  const { data: evidence } = useQuery<SubcapEvidenceHeatmap>({
    queryKey: ['vendor-subcap-evidence'],
    queryFn: () => apiGet<SubcapEvidenceHeatmap>('/vendor-intel/subcap-evidence'),
    enabled: tab === 'evidence',
  });

  const refresh = useMutation({
    mutationFn: () =>
      apiPost<{ vendors_loaded: number; adoption_rows: number; events_loaded: number }>(
        '/vendor-intel/refresh',
      ),
    onSettled: () => qc.invalidateQueries(),
  });

  const cellByKey = useMemo(() => {
    const map = new Map<string, VendorHeatmap['cells'][number]>();
    for (const c of heatmap?.cells || []) {
      map.set(`${c.vendor_id}__${c.cohort_id}`, c);
    }
    return map;
  }, [heatmap]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold text-zen-dark-green">Partner Intelligence</h1>
          <p className="text-sm text-zen-dark-teal/80 max-w-3xl">
            Six Zennify partners — Salesforce, nCino, Databricks, Twilio, MuleSoft, Agentforce —
            tracked across three lenses: <b>Adoption</b> (per peer cohort), <b>Releases</b> (last
            90 days of release notes, parsed and L1-mapped), and <b>Catalogue gaps</b>
            (high-confidence partner features the catalogue doesn't yet reflect).
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => scan.mutate()}
            disabled={scan.isPending}
            className="bg-zen-dark-teal hover:bg-zen-dark-green text-white text-xs font-medium px-3 py-1.5 rounded transition-colors disabled:opacity-50"
            title="Re-run release-notes scan + L1 mapping (Gemini Flash)"
          >
            <Wand2 size={12} className={`inline mr-1 ${scan.isPending ? 'animate-pulse' : ''}`} />
            {scan.isPending ? 'Scanning…' : 'Scan releases'}
          </button>
          <button
            type="button"
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending}
            className="bg-zen-teal hover:bg-zen-dark-teal text-white text-xs font-medium px-3 py-1.5 rounded transition-colors disabled:opacity-50"
          >
            <RefreshCw size={12} className={`inline mr-1 ${refresh.isPending ? 'animate-spin' : ''}`} />
            Refresh adoption
          </button>
        </div>
      </div>

      {scan.data && (
        <div className="bg-white border border-zen-separator rounded-lg p-3 text-xs text-zen-text-gray flex items-center gap-2">
          <Sparkles size={14} className="text-zen-teal" />
          Scanned <strong>{scan.data.entries_seen}</strong> releases ·{' '}
          <strong>{scan.data.features_extracted}</strong> features extracted ·{' '}
          <strong>{scan.data.suggestions_created}</strong> catalogue-gap suggestions filed.
        </div>
      )}
      {refresh.data && (
        <div className="bg-white border border-zen-separator rounded-lg p-3 text-xs text-zen-text-gray flex items-center gap-2">
          <CheckCircle2 size={14} className="text-zen-teal" />
          Adoption refresh: <strong>{refresh.data.vendors_loaded}</strong> vendors ·{' '}
          <strong>{refresh.data.adoption_rows}</strong> rows ·{' '}
          <strong>{refresh.data.events_loaded}</strong> events.
        </div>
      )}

      {/* Tabs */}
      <div className="inline-flex items-center bg-zen-ice rounded-lg border border-zen-separator p-0.5">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`text-xs px-3 py-1 rounded ${
              tab === t.key
                ? 'bg-white shadow-sm text-zen-dark-green font-medium'
                : 'text-zen-text-gray'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* TAB: SUBCAP EVIDENCE (Phase 2.3) — vendor × subcap matrix
          derived from real signals (vendor_events joined to
          news_items.impact.affected_subcaps), not technographic
          adoption percentages. Cell color = highest magnitude across
          all matching events. */}
      {tab === 'evidence' && (
        <div className="space-y-3">
          <div className="bg-white rounded-lg border border-zen-separator p-3">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-xs uppercase font-semibold tracking-wider text-zen-dark-green">
                Vendor × Subcap evidence
              </h2>
              {evidence && (
                <span className="text-[10px] text-zen-muted-text">
                  {evidence.cells.length} cells from {evidence.total_events_joined} events
                </span>
              )}
            </div>
            {!evidence || evidence.cells.length === 0 ? (
              <div className="text-xs text-zen-muted-text italic">
                No vendor events joined to news impact yet. Run a news refresh,
                synthesise impact (in News Watch), and refresh vendor adoption to
                populate this view.
              </div>
            ) : (
              <div className="overflow-x-auto max-h-[640px]">
                <table className="text-xs min-w-full">
                  <thead className="text-zen-text-gray sticky top-0 bg-white">
                    <tr>
                      <th className="text-left px-2 py-1 border-b border-zen-separator">
                        Vendor
                      </th>
                      <th className="text-left px-2 py-1 border-b border-zen-separator">
                        Subcap
                      </th>
                      <th className="text-left px-2 py-1 border-b border-zen-separator">
                        Magnitude
                      </th>
                      <th className="text-right px-2 py-1 border-b border-zen-separator">
                        Events
                      </th>
                      <th className="text-left px-2 py-1 border-b border-zen-separator">
                        Latest
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {evidence.cells
                      .slice()
                      .sort((a, b) => {
                        const order = { HIGH: 0, MEDIUM: 1, LOW: 2 } as const;
                        return (
                          order[a.magnitude] - order[b.magnitude] ||
                          b.event_count - a.event_count
                        );
                      })
                      .map((c) => (
                        <tr
                          key={`${c.vendor_id}::${c.sub_cap_id}`}
                          className="border-b border-zen-separator/60"
                        >
                          <td className="px-2 py-1 text-zen-dark-green">
                            {c.vendor_name || c.vendor_id}
                          </td>
                          <td className="px-2 py-1">
                            <a
                              href={`/subcap?id=${encodeURIComponent(c.sub_cap_id)}`}
                              className="font-mono text-zen-teal hover:text-zen-dark-teal"
                            >
                              {c.sub_cap_id}
                            </a>
                          </td>
                          <td className="px-2 py-1">
                            <span
                              className={`text-[10px] uppercase tracking-wider rounded px-1.5 py-0.5 ${EVIDENCE_MAG_BG[c.magnitude]}`}
                            >
                              {c.magnitude}
                            </span>
                          </td>
                          <td className="px-2 py-1 text-right text-zen-text-gray">
                            {c.event_count}
                          </td>
                          <td className="px-2 py-1 text-zen-text-gray">
                            {c.latest_event
                              ? new Date(c.latest_event).toLocaleDateString()
                              : '—'}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB: RELEASES */}
      {tab === 'releases' && (
        <div className="space-y-3">
          {/* Partner pills filter */}
          <div className="flex flex-wrap gap-1">
            <button
              type="button"
              onClick={() => setSelectedPartner(null)}
              className={`text-[11px] px-2 py-1 rounded ${
                !selectedPartner
                  ? 'bg-zen-dark-green text-white'
                  : 'bg-zen-ice text-zen-text-gray hover:bg-zen-ice/80'
              }`}
            >
              All partners
            </button>
            {(partners || []).map((p) => (
              <button
                key={p.code}
                type="button"
                onClick={() => setSelectedPartner(p.code)}
                className={`text-[11px] px-2 py-1 rounded ${
                  selectedPartner === p.code
                    ? 'bg-zen-dark-green text-white'
                    : 'bg-zen-ice text-zen-text-gray hover:bg-zen-ice/80'
                }`}
              >
                {p.name}
              </button>
            ))}
          </div>

          {(releases || []).length === 0 && (
            <div className="bg-white rounded-lg border border-zen-separator p-6 text-center text-sm text-zen-text-gray">
              No releases scanned yet. Click <strong>Scan releases</strong> to run the partner
              release-notes pipeline.
            </div>
          )}

          <ul className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {(releases || []).map((r) => (
              <li
                key={r.release_id}
                className="bg-white rounded-lg border border-zen-separator p-3 flex flex-col"
              >
                <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-zen-muted-text">
                  <span className="font-mono">{r.partner_name}</span>
                  <span>·</span>
                  <span>{new Date(r.published_at).toLocaleDateString()}</span>
                  {r.url && (
                    <a
                      href={r.url}
                      target="_blank"
                      rel="noreferrer"
                      className="ml-auto text-zen-teal hover:text-zen-dark-teal inline-flex items-center gap-0.5"
                    >
                      source <ExternalLink size={9} />
                    </a>
                  )}
                </div>
                <h3 className="text-sm font-semibold text-zen-dark-green mt-1">
                  {r.url ? (
                    <a href={r.url} target="_blank" rel="noreferrer" className="hover:underline">
                      {r.title}
                    </a>
                  ) : (
                    r.title
                  )}
                </h3>
                {r.summary && (
                  <p className="text-xs text-zen-text-gray mt-1 line-clamp-3">{r.summary}</p>
                )}
                {(r.features || []).length > 0 && (
                  <ul className="mt-2 space-y-1.5 border-t border-zen-separator/40 pt-2">
                    {(r.features || []).map((f, i) => (
                      <li key={i} className="text-xs">
                        <div className="flex items-baseline gap-2 flex-wrap">
                          <span className={`text-[10px] uppercase rounded px-1.5 py-0.5 ${IMPACT_BADGE[f.impact_class]}`}>
                            {f.impact_class.replace(/_/g, ' ')}
                          </span>
                          <span className="font-medium text-zen-dark-green">{f.feature}</span>
                          {f.is_gap && (
                            <span className="text-[10px] uppercase tracking-wider rounded px-1.5 py-0.5 bg-zen-orange text-white inline-flex items-center gap-0.5">
                              <Flame size={9} /> gap
                            </span>
                          )}
                        </div>
                        {f.summary && (
                          <p className="text-[11px] text-zen-text-gray mt-0.5">{f.summary}</p>
                        )}
                        {f.mapped_l1 && (
                          <div className="text-[10px] text-zen-muted-text mt-0.5">
                            Mapped L1: <span className="text-zen-dark-teal font-medium">{f.mapped_l1}</span>
                            {typeof f.score === 'number' && (
                              <span className="text-zen-muted-text"> · score {f.score.toFixed(2)}</span>
                            )}
                          </div>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* TAB: CATALOGUE GAPS */}
      {tab === 'gaps' && (
        <div className="space-y-3">
          {(gaps || []).length === 0 && (
            <div className="bg-white rounded-lg border border-zen-separator p-6 text-center text-sm text-zen-text-gray">
              No catalogue gaps surfaced. Run <strong>Scan releases</strong> first; the pipeline
              flags features whose semantic mapping confidence is high but the catalogue doesn't
              already cover the feature on the mapped L1.
            </div>
          )}
          <ul className="space-y-3">
            {(gaps || []).map((g) => (
              <li
                key={g.l1_capability}
                className="bg-white rounded-lg border border-zen-separator p-3"
              >
                <div className="flex items-baseline gap-2 flex-wrap">
                  <Layers size={14} className="text-zen-teal" />
                  <h3 className="text-sm font-semibold text-zen-dark-green">{g.l1_capability}</h3>
                  <span className="text-[10px] uppercase tracking-wider rounded px-1.5 py-0.5 bg-zen-orange text-white">
                    {g.count} feature{g.count === 1 ? '' : 's'}
                  </span>
                  <span className="text-[10px] text-zen-muted-text ml-auto">
                    last seen {new Date(g.last_seen).toLocaleDateString()}
                  </span>
                </div>
                <div className="text-[11px] text-zen-text-gray mt-0.5">
                  Surfaced by:{' '}
                  {g.partners.map((p, i) => (
                    <span key={p} className="font-mono">
                      {p}
                      {i < g.partners.length - 1 && ', '}
                    </span>
                  ))}
                </div>
                <ul className="mt-2 space-y-1.5 border-t border-zen-separator/40 pt-2">
                  {g.features.map((f, i) => (
                    <li key={i} className="text-xs">
                      <div className="flex items-baseline gap-2 flex-wrap">
                        <span className="font-mono text-[10px] text-zen-teal">{f.partner_code}</span>
                        <span className="font-medium text-zen-dark-green">{f.feature}</span>
                        {typeof f.score === 'number' && (
                          <span className="text-[10px] text-zen-muted-text">conf {f.score.toFixed(2)}</span>
                        )}
                        {f.release_url && (
                          <a
                            href={f.release_url}
                            target="_blank"
                            rel="noreferrer"
                            className="ml-auto text-zen-teal hover:text-zen-dark-teal inline-flex items-center gap-0.5 text-[10px]"
                          >
                            source <ExternalLink size={9} />
                          </a>
                        )}
                      </div>
                      <p className="text-[11px] text-zen-text-gray mt-0.5">{f.summary}</p>
                    </li>
                  ))}
                </ul>
                <div className="mt-2 text-[10px] text-zen-muted-text">
                  Review the queued <Link to="/suggestions" className="text-zen-teal hover:text-zen-dark-teal underline">AI Suggestions</Link>{' '}
                  to apply or reject these as catalogue edits.
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* TAB: ADOPTION (existing flow) */}
      {tab === 'adoption' && (
        <>
          <div className="bg-white rounded-lg border border-zen-separator p-3">
            <h2 className="text-xs uppercase font-semibold tracking-wider text-zen-dark-green mb-2">
              Vendor × Cohort heatmap
            </h2>
            {!heatmap || heatmap.vendors.length === 0 ? (
              <div className="text-xs text-zen-muted-text italic">
                No adoption data yet. Click <strong>Refresh adoption</strong> to ingest from
                technographic seeds.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="text-xs min-w-full">
                  <thead className="text-zen-text-gray">
                    <tr>
                      <th className="text-left px-2 py-1">Vendor</th>
                      {heatmap.cohorts.map((c) => (
                        <th key={c} className="text-right px-2 py-1 font-mono text-[10px]">
                          {c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {heatmap.vendors.map((vid) => {
                      const profile = (vendors || []).find((v) => v.vendor_id === vid);
                      return (
                        <tr
                          key={vid}
                          className={`hover:bg-zen-ice/40 ${
                            selectedVendor === vid ? 'bg-zen-ice' : ''
                          }`}
                        >
                          <td className="px-2 py-1">
                            <button
                              onClick={() =>
                                setSelectedVendor(selectedVendor === vid ? null : vid)
                              }
                              className="text-zen-dark-green hover:text-zen-teal text-left"
                            >
                              {profile?.name || vid}
                            </button>
                            {profile?.category && (
                              <span className="ml-2 text-[10px] uppercase rounded px-1 bg-zen-light-green/40 text-zen-dark-teal">
                                {profile.category}
                              </span>
                            )}
                          </td>
                          {heatmap.cohorts.map((cid) => {
                            const cell = cellByKey.get(`${vid}__${cid}`);
                            if (!cell || cell.adoption_pct === 0) {
                              return (
                                <td
                                  key={cid}
                                  className="text-right px-2 py-1 text-zen-muted-text"
                                >
                                  ·
                                </td>
                              );
                            }
                            const pct = cell.adoption_pct;
                            const intensity = Math.min(1, pct / 100);
                            return (
                              <td
                                key={cid}
                                className="text-right px-2 py-1 font-mono text-[10px]"
                                style={{
                                  backgroundColor: `rgba(20, 116, 110, ${0.10 + intensity * 0.50})`,
                                  color: intensity > 0.5 ? 'white' : '#1C4A4D',
                                }}
                                title={`${cell.adopters.join(', ')} of ${cell.cohort_size}`}
                              >
                                {pct.toFixed(0)}%
                              </td>
                            );
                          })}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <div className="bg-white rounded-lg border border-zen-separator p-3">
              <h2 className="text-xs uppercase font-semibold tracking-wider text-zen-dark-green mb-2">
                Vendor profiles ({(vendors || []).length})
              </h2>
              <ul className="divide-y divide-zen-separator/40 max-h-[640px] overflow-auto">
                {(vendors || []).map((v) => (
                  <li
                    key={v.vendor_id}
                    className={`py-2 cursor-pointer hover:bg-zen-ice/40 rounded px-1 ${
                      selectedVendor === v.vendor_id ? 'bg-zen-ice' : ''
                    }`}
                    onClick={() =>
                      setSelectedVendor(selectedVendor === v.vendor_id ? null : v.vendor_id)
                    }
                  >
                    <div className="flex items-center gap-2 text-xs">
                      <span className="font-medium text-zen-dark-green">{v.name}</span>
                      {v.category && (
                        <span className="text-[10px] uppercase rounded px-1 bg-zen-light-green/40 text-zen-dark-teal">
                          {v.category}
                        </span>
                      )}
                      <span className="ml-auto text-[10px] text-zen-text-gray">
                        conf {(v.avg_confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div className="text-[10px] text-zen-text-gray mt-0.5 flex flex-wrap gap-x-2">
                      <span className="inline-flex items-center gap-0.5">
                        <Building2 size={9} />
                        {v.companies.length} companies
                      </span>
                      <span>{v.cohorts.length} cohorts</span>
                      <span>{v.news_mentions} news</span>
                      {v.ai_signal_avg != null && <span>AI {v.ai_signal_avg}</span>}
                    </div>
                  </li>
                ))}
              </ul>
            </div>

            <div className="bg-white rounded-lg border border-zen-separator p-3">
              <h2 className="text-xs uppercase font-semibold tracking-wider text-zen-dark-green mb-2">
                Events {selectedVendor && (
                  <span className="text-zen-muted-text normal-case font-normal">
                    — filtered
                  </span>
                )}
              </h2>
              <ul className="divide-y divide-zen-separator/40 max-h-[640px] overflow-auto">
                {(events || []).slice(0, 50).map((e) => (
                  <li key={e.id} className="py-2 text-xs">
                    <div className="flex items-center gap-2 text-[10px] text-zen-text-gray">
                      <span className="font-mono">{e.vendor_name}</span>
                      <span>·</span>
                      <span className="uppercase">{e.kind}</span>
                      {e.url && (
                        <a
                          href={e.url}
                          target="_blank"
                          rel="noreferrer"
                          className="ml-auto inline-flex items-center gap-0.5 text-zen-teal hover:text-zen-dark-teal"
                        >
                          source <ExternalLink size={9} />
                        </a>
                      )}
                    </div>
                    <div className="font-medium text-zen-dark-green mt-0.5">{e.title}</div>
                    <div className="text-[10px] text-zen-muted-text mt-0.5">
                      {e.published_at && new Date(e.published_at).toLocaleDateString()} · {e.source}
                    </div>
                  </li>
                ))}
                {(events || []).length === 0 && (
                  <li className="text-zen-muted-text italic text-xs py-1">
                    No events for this filter.
                  </li>
                )}
              </ul>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
