import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { ChevronRight } from 'lucide-react';
import { apiGet, type Subvertical, type ValueChainAtlas as Atlas } from '@/lib/api';

export default function ValueChainAtlas() {
  const [subvertical, setSubvertical] = useState<string>('');
  const [focusedCluster, setFocusedCluster] = useState<string | null>(null);

  const { data: subverticals } = useQuery<Subvertical[]>({
    queryKey: ['subverticals'],
    queryFn: () => apiGet<Subvertical[]>('/lens/subverticals'),
  });

  const { data: atlas, isLoading } = useQuery<Atlas>({
    queryKey: ['atlas', subvertical],
    queryFn: () =>
      apiGet<Atlas>(`/lens/value-chain-atlas${subvertical ? `?subvertical_code=${subvertical}` : ''}`),
  });

  // The 8 canonical clusters are ordered (VCC-01 → VCC-08). Filter out
  // VCC-00 (Unclassified) from the flow strip; surface it separately below.
  const ordered = (atlas?.clusters || []).filter((c) => c.code !== 'VCC-00');
  const unclassified = (atlas?.clusters || []).find((c) => c.code === 'VCC-00');
  const focused = ordered.find((c) => c.code === focusedCluster) || null;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-zen-dark-green">Value Chain Atlas</h1>
        <p className="text-sm text-zen-dark-teal/80 max-w-3xl">
          The eight MECE value-chain clusters that every financial-services subcapability flows
          through — Market → Acquire & Onboard → Serve & Engage → Advise & Sell → Originate &
          Decision → Portfolio & Risk → Settle & Service → Operate & Platform. Use the
          subvertical lens to see which subcaps land in each stage.
        </p>
      </div>

      <div className="bg-white rounded-lg border border-zen-separator p-3 flex items-center gap-3 text-sm">
        <label className="text-zen-text-gray">Subvertical lens</label>
        <select
          value={subvertical}
          onChange={(e) => {
            setSubvertical(e.target.value);
            setFocusedCluster(null);
          }}
          className="border border-zen-separator rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-zen-teal"
        >
          <option value="">All subverticals</option>
          {subverticals?.map((sv) => (
            <option key={sv.code} value={sv.code}>
              {sv.code} — {sv.name}
            </option>
          ))}
        </select>
        {focusedCluster && (
          <button
            type="button"
            onClick={() => setFocusedCluster(null)}
            className="text-xs text-zen-teal hover:text-zen-dark-teal underline ml-auto"
          >
            Clear focus
          </button>
        )}
      </div>

      {isLoading && <div className="text-xs text-zen-muted-text">Loading atlas…</div>}

      {/* Horizontal flow strip — scrolls on small screens, 8-up on desktop */}
      {atlas && (
        <div className="overflow-x-auto pb-2">
          <div className="flex items-stretch gap-1 min-w-max">
            {ordered.map((c, i) => {
              const isFocused = focusedCluster === c.code;
              const dimmed = focusedCluster && !isFocused;
              return (
                <div key={c.code} className="flex items-stretch">
                  <button
                    type="button"
                    onClick={() => setFocusedCluster(isFocused ? null : c.code)}
                    className={[
                      'w-[180px] rounded-lg p-3 text-left transition-all duration-200 flex flex-col',
                      'border-t-4 bg-white shadow-sm hover:shadow-md hover:-translate-y-0.5',
                      isFocused ? 'ring-2 ring-zen-teal' : '',
                      dimmed ? 'opacity-40' : '',
                    ].join(' ')}
                    style={{ borderTopColor: c.color || '#27BBAF' }}
                    aria-label={`${c.code} ${c.name}`}
                  >
                    <div className="text-[9px] uppercase tracking-wider font-mono text-zen-muted-text flex items-center gap-1">
                      <span>Stage {i + 1}</span>
                      <span aria-hidden>·</span>
                      <span>{c.code}</span>
                    </div>
                    <div className="text-sm font-semibold text-zen-dark-green mt-0.5">{c.name}</div>
                    <div className="mt-auto pt-2 flex items-baseline justify-between">
                      <span className="text-[10px] text-zen-muted-text">subcaps</span>
                      <span className="text-lg font-semibold text-zen-dark-green leading-none">
                        {c.total_subcaps}
                      </span>
                    </div>
                  </button>
                  {i < ordered.length - 1 && (
                    <ChevronRight
                      size={16}
                      className="text-zen-teal/40 self-center mx-0.5 shrink-0"
                      aria-hidden
                    />
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Detail panel for the focused stage */}
      {focused && (
        <div
          className="bg-white rounded-lg border border-zen-separator p-4"
          style={{ borderLeftWidth: 4, borderLeftColor: focused.color || '#27BBAF' }}
        >
          <div className="flex items-baseline justify-between mb-2">
            <div>
              <div className="text-[10px] uppercase tracking-wider font-mono text-zen-muted-text">
                {focused.code}
              </div>
              <h2 className="text-lg font-semibold text-zen-dark-green">{focused.name}</h2>
            </div>
            <div className="text-xs text-zen-text-gray">
              {focused.stages.length} stages · {focused.total_subcaps} subcaps
            </div>
          </div>
          {focused.stages.length === 0 ? (
            <div className="text-xs text-zen-muted-text italic">
              No stages mapped to this cluster for the current lens.
            </div>
          ) : (
            <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {focused.stages.map((s, i) => (
                <li
                  key={i}
                  className="text-xs border border-zen-separator rounded px-2 py-1.5 flex items-center gap-1.5 bg-zen-ice/50"
                >
                  <span className="font-mono text-[9px] bg-zen-light-green/60 text-zen-dark-teal rounded px-1">
                    {s.subvertical_code}
                  </span>
                  <span className="flex-1 truncate" title={s.name}>
                    {s.name}
                  </span>
                  <span className="text-[10px] text-zen-muted-text">×{s.subcap_count}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Unclassified bucket — surfaces hygiene problems */}
      {unclassified && unclassified.stages.length > 0 && (
        <div className="bg-zen-light-orange/30 border border-zen-orange/40 rounded-lg p-3">
          <div className="text-xs uppercase font-semibold tracking-wider text-zen-orange mb-1">
            Unclassified — needs taxonomy review
          </div>
          <div className="text-xs text-zen-text-gray">
            {unclassified.stages.length} stage names didn't match any cluster keyword. Examples:{' '}
            {unclassified.stages.slice(0, 6).map((s) => s.name).join(', ')}
            {unclassified.stages.length > 6 && '…'}
          </div>
        </div>
      )}
    </div>
  );
}
