import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { ArrowRight } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { apiGet, type Subcap, type Subvertical, type SubverticalCompare as SCResp } from '@/lib/api';

type GapsResp = {
  from: { code: string; name: string } | null;
  to: { code: string; name: string } | null;
  common: string[];
  only_in_from: { sub_cap_id: string; sub_cap_name?: string; category_id?: string; l1_capability?: string }[];
  only_in_to: { sub_cap_id: string; sub_cap_name?: string; category_id?: string; l1_capability?: string }[];
};

export default function SubverticalCompare() {
  const [params, setParams] = useSearchParams();
  const [mode, setMode] = useState<'subcap' | 'gap'>(
    params.get('mode') === 'gap' ? 'gap' : 'subcap',
  );
  const initial = params.get('id') || 'P1C1.1.1';
  const [id, setId] = useState(initial);
  const [fromCode, setFromCode] = useState(params.get('from') || 'fs-retail-banking');
  const [toCode, setToCode] = useState(params.get('to') || 'fs-credit-unions');

  const { data: subcaps } = useQuery<Subcap[]>({
    queryKey: ['subcaps-list'],
    queryFn: () => apiGet<Subcap[]>('/catalogue/subcaps'),
  });

  const { data: subverticals } = useQuery<Subvertical[]>({
    queryKey: ['subverticals'],
    queryFn: () => apiGet<Subvertical[]>('/lens/subverticals'),
  });

  const { data: compare, isLoading: cmpLoading } = useQuery<SCResp>({
    queryKey: ['sv-compare', id],
    queryFn: () => apiGet<SCResp>(`/lens/subvertical-compare/${encodeURIComponent(id)}`),
    enabled: mode === 'subcap' && !!id,
  });

  const { data: gaps, isLoading: gapLoading } = useQuery<GapsResp>({
    queryKey: ['sv-gaps', fromCode, toCode],
    queryFn: () =>
      apiGet<GapsResp>(
        `/lens/subvertical-gaps?from_code=${encodeURIComponent(fromCode)}&to_code=${encodeURIComponent(toCode)}`,
      ),
    enabled: mode === 'gap' && fromCode !== toCode,
  });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-zen-dark-green">Subvertical Compare</h1>
        <p className="text-sm text-zen-dark-teal/80 max-w-3xl">
          Two views: <b>By subcap</b> shows how a single subcap maps across the 10 subverticals
          (stages + clusters). <b>Gaps</b> shows the asymmetric coverage between two subverticals
          — subcaps present in one but not the other. The "only in the comparison" set surfaces
          expansion opportunities.
        </p>
      </div>

      {/* Mode toggle */}
      <div className="inline-flex items-center bg-zen-ice rounded-lg border border-zen-separator p-0.5">
        {(['subcap', 'gap'] as const).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => {
              setMode(m);
              const next = new URLSearchParams(params);
              next.set('mode', m);
              setParams(next);
            }}
            className={`text-xs px-3 py-1 rounded ${
              mode === m
                ? 'bg-white shadow-sm text-zen-dark-green font-medium'
                : 'text-zen-text-gray'
            }`}
          >
            {m === 'subcap' ? 'By subcap' : 'Subvertical gaps'}
          </button>
        ))}
      </div>

      {/* MODE: by subcap (existing flow) */}
      {mode === 'subcap' && (
        <>
          <div className="bg-white rounded-lg border border-zen-separator p-3 flex items-center gap-2 text-sm">
            <label className="text-zen-text-gray">Subcap</label>
            <select
              value={id}
              onChange={(e) => {
                setId(e.target.value);
                const next = new URLSearchParams(params);
                next.set('id', e.target.value);
                setParams(next);
              }}
              className="border border-zen-separator rounded px-2 py-1 text-xs flex-1 max-w-md focus:outline-none focus:ring-1 focus:ring-zen-teal"
            >
              {subcaps?.slice(0, 500).map((s) => (
                <option key={s.sub_cap_id} value={s.sub_cap_id}>
                  {s.sub_cap_id} — {s.sub_cap_name}
                </option>
              ))}
            </select>
          </div>

          {cmpLoading && <div className="text-xs text-zen-muted-text">Loading…</div>}

          {compare && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {compare.rows.map((row) => (
                <div
                  key={row.subvertical_code}
                  className={`bg-white rounded-lg border p-3 ${
                    row.applicable ? 'border-zen-separator' : 'border-zen-separator/50 opacity-60'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <div>
                      <span className="font-mono text-[10px] bg-zen-dark-green text-white rounded px-1.5 py-0.5 mr-2">
                        {row.subvertical_code}
                      </span>
                      <span className="text-sm font-semibold text-zen-dark-green">
                        {row.subvertical_name}
                      </span>
                    </div>
                    {!row.applicable && (
                      <span className="text-[10px] text-zen-muted-text italic">N/A</span>
                    )}
                  </div>
                  {row.stages.length > 0 && (
                    <ul className="space-y-0.5">
                      {row.stages.map((s, i) => (
                        <li key={i} className="text-xs text-zen-text-gray flex items-center gap-2">
                          <span className="font-mono text-[9px] bg-zen-light-green/50 rounded px-1">
                            {s.cluster}
                          </span>
                          <span className="flex-1 truncate">{s.name}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* MODE: gap analysis */}
      {mode === 'gap' && (
        <>
          <div className="bg-white rounded-lg border border-zen-separator p-3 flex flex-wrap items-center gap-2 text-sm">
            <SVSelect value={fromCode} onChange={setFromCode} options={subverticals} label="From" />
            <ArrowRight size={16} className="text-zen-muted-text" />
            <SVSelect value={toCode} onChange={setToCode} options={subverticals} label="To" />
          </div>

          {fromCode === toCode && (
            <div className="text-xs text-zen-orange italic">
              Pick two different subverticals to compare.
            </div>
          )}

          {gapLoading && <div className="text-xs text-zen-muted-text">Loading…</div>}

          {gaps && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
              <GapPanel
                title="Only in From"
                items={gaps.only_in_from}
                accent="bg-zen-dark-purple"
                description={`Subcaps tagged for ${gaps.from?.name} but not ${gaps.to?.name}.`}
              />
              <GapPanel
                title="Common"
                items={gaps.common.map((id) => ({ sub_cap_id: id }))}
                accent="bg-zen-teal"
                description={`Tagged for both subverticals — your shared playbook.`}
                showName={false}
              />
              <GapPanel
                title="Only in To — expansion ops"
                items={gaps.only_in_to}
                accent="bg-zen-orange"
                description={`Subcaps ${gaps.to?.name} is practising but ${gaps.from?.name} hasn't tagged yet.`}
              />
            </div>
          )}
        </>
      )}
    </div>
  );
}

function SVSelect({
  value,
  onChange,
  options,
  label,
}: {
  value: string;
  onChange: (v: string) => void;
  options: Subvertical[] | undefined;
  label: string;
}) {
  return (
    <label className="text-xs flex items-center gap-1">
      <span className="text-zen-text-gray">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="border border-zen-separator rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-zen-teal"
      >
        {options?.map((sv) => (
          <option key={sv.code} value={sv.code}>
            {sv.name}
          </option>
        ))}
      </select>
    </label>
  );
}

function GapPanel({
  title,
  items,
  accent,
  description,
  showName = true,
}: {
  title: string;
  items: { sub_cap_id: string; sub_cap_name?: string; l1_capability?: string }[];
  accent: string;
  description?: string;
  showName?: boolean;
}) {
  return (
    <div className="bg-white rounded-lg border border-zen-separator overflow-hidden flex flex-col">
      <div className="px-3 py-2 border-b border-zen-separator">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${accent}`} aria-hidden />
          <h3 className="text-sm font-semibold text-zen-dark-green">{title}</h3>
          <span className="ml-auto text-xs text-zen-muted-text">{items.length}</span>
        </div>
        {description && <p className="text-[11px] text-zen-text-gray mt-1">{description}</p>}
      </div>
      <ul className="divide-y divide-zen-separator/50 max-h-[500px] overflow-auto">
        {items.length === 0 ? (
          <li className="px-3 py-3 text-xs text-zen-muted-text italic">No subcaps in this bucket.</li>
        ) : (
          items.map((it) => (
            <li key={it.sub_cap_id} className="px-3 py-1.5 text-xs">
              <Link
                to={`/subcap?id=${encodeURIComponent(it.sub_cap_id)}`}
                className="hover:bg-zen-ice -mx-3 -my-1.5 px-3 py-1.5 flex items-baseline gap-2 block"
              >
                <span className="font-mono text-[10px] text-zen-teal">{it.sub_cap_id}</span>
                {showName && it.sub_cap_name && (
                  <span className="text-zen-dark-green truncate">{it.sub_cap_name}</span>
                )}
              </Link>
            </li>
          ))
        )}
      </ul>
    </div>
  );
}
