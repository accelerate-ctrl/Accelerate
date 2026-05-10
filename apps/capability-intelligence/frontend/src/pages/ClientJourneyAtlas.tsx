import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Building2, Download, RefreshCw, Sparkles, Layers } from 'lucide-react';
import { Link } from 'react-router-dom';
import { apiGet, apiPost, type ClientJourney, type DmaPacket } from '@/lib/api';

const STATE_BADGE: Record<string, string> = {
  EMERGING: 'bg-zen-light-orange text-zen-dark-green',
  RISING: 'bg-zen-teal text-white',
  STABLE: 'bg-zen-light-green/70 text-zen-dark-green',
  DECLINING: 'bg-zen-light-orange/70 text-zen-dark-green',
  FADING: 'bg-zen-orange/40 text-zen-dark-green',
  DEAD: 'bg-zen-dark-teal/40 text-zen-white-green',
};

export default function ClientJourneyAtlas() {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<string | null>(null);

  const { data: journeys } = useQuery<ClientJourney[]>({
    queryKey: ['client-journeys'],
    queryFn: () => apiGet<ClientJourney[]>('/clients?limit=200'),
  });

  const { data: detail } = useQuery<ClientJourney>({
    queryKey: ['client-journey', selected],
    enabled: !!selected,
    queryFn: () => apiGet<ClientJourney>(`/clients/${encodeURIComponent(selected || '')}/journey`),
  });

  const refresh = useMutation({
    mutationFn: () => apiPost<{ clients_built: number; client_names: string[] }>('/clients/refresh'),
    onSettled: () => qc.invalidateQueries(),
  });

  const exportPacket = async () => {
    if (!selected) return;
    const packet = await apiGet<DmaPacket>(`/clients/${encodeURIComponent(selected)}/dma-packet`);
    const blob = new Blob([JSON.stringify(packet, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `dma-packet-${selected.replace(/\s+/g, '_')}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zen-dark-green">Client Journey Atlas</h1>
          <p className="text-sm text-zen-dark-teal/80">
            Per-client view of touched subcaps with lifecycle state + vendor stack.
            <strong className="ml-1">DMA Packet</strong> exports the full handoff as JSON.
          </p>
        </div>
        <button
          onClick={() => refresh.mutate()}
          disabled={refresh.isPending}
          className="bg-zen-teal hover:bg-zen-dark-teal text-white text-xs font-medium px-3 py-1.5 rounded transition-colors disabled:opacity-50"
        >
          <RefreshCw size={12} className={`inline mr-1 ${refresh.isPending ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <div className="lg:col-span-1 bg-white rounded-lg border border-zen-light-green/40 p-3">
          <h2 className="text-xs uppercase font-semibold tracking-wider text-zen-dark-green mb-2">
            Clients ({(journeys || []).length})
          </h2>
          <ul className="divide-y divide-zen-light-green/30 max-h-[640px] overflow-auto">
            {(journeys || []).map((j) => (
              <li key={j.client_name}>
                <button
                  onClick={() => setSelected(j.client_name)}
                  className={`w-full text-left p-2 rounded hover:bg-zen-white-green/60 ${selected === j.client_name ? 'bg-zen-white-green' : ''}`}
                >
                  <div className="flex items-center gap-2">
                    <Building2 size={12} className="text-zen-teal" />
                    <span className="text-sm font-medium text-zen-dark-green">{j.client_name}</span>
                  </div>
                  <div className="text-[10px] text-zen-dark-teal/60 mt-0.5 flex flex-wrap gap-x-2">
                    {j.sow_count_active > 0 && <span>{j.sow_count_active} active</span>}
                    {j.sow_count_prospect > 0 && <span>{j.sow_count_prospect} prospect</span>}
                    {j.sow_count_inactive > 0 && <span>{j.sow_count_inactive} inactive</span>}
                    <span className="ml-auto">{j.touched_subcaps.length} subcaps</span>
                  </div>
                </button>
              </li>
            ))}
            {(journeys || []).length === 0 && (
              <li className="text-xs text-zen-dark-teal/60 italic py-2">
                No journeys yet — click <strong>Refresh</strong>.
              </li>
            )}
          </ul>
        </div>

        <div className="lg:col-span-2">
          {!detail && (
            <div className="bg-white rounded-lg border border-zen-light-green/40 p-6 text-center text-sm text-zen-dark-teal/70">
              Pick a client on the left to see their journey + vendor stack + DMA packet.
            </div>
          )}
          {detail && <JourneyPanel journey={detail} onExport={exportPacket} />}
        </div>
      </div>
    </div>
  );
}

function JourneyPanel({ journey, onExport }: { journey: ClientJourney; onExport: () => void }) {
  return (
    <div className="space-y-3">
      <div className="bg-white rounded-lg border border-zen-light-green/40 p-3">
        <div className="flex items-center gap-2">
          <Building2 size={14} className="text-zen-teal" />
          <h2 className="text-base font-semibold text-zen-dark-green">{journey.client_name}</h2>
          <button
            onClick={onExport}
            className="ml-auto bg-zen-teal hover:bg-zen-dark-teal text-white text-[10px] font-medium px-2 py-1 rounded inline-flex items-center gap-1"
          >
            <Download size={11} /> DMA Packet
          </button>
        </div>
        <div className="text-[10px] text-zen-dark-teal/70 mt-1 flex flex-wrap gap-x-2">
          {journey.subverticals.map((s) => (
            <span key={s} className="rounded px-1 bg-zen-light-orange/60 text-zen-dark-green">{s}</span>
          ))}
          {journey.cohorts.map((c) => (
            <span key={c} className="font-mono rounded px-1 bg-zen-light-green/40 text-zen-dark-teal">{c}</span>
          ))}
          {journey.asset_size_usd_bn != null && (
            <span>${journey.asset_size_usd_bn}B AUM</span>
          )}
        </div>
        <div className="grid grid-cols-4 gap-2 mt-2 text-[11px]">
          <KPI label="Active SOWs" value={journey.sow_count_active} />
          <KPI label="Prospect" value={journey.sow_count_prospect} />
          <KPI label="Inactive" value={journey.sow_count_inactive} />
          <KPI label="Subcaps" value={journey.touched_subcaps.length} />
        </div>
      </div>

      <div className="bg-white rounded-lg border border-zen-light-green/40 p-3">
        <h3 className="text-xs uppercase font-semibold tracking-wider text-zen-dark-green mb-2 flex items-center gap-1">
          <Layers size={12} /> Touched subcaps
        </h3>
        <ul className="divide-y divide-zen-light-green/30 max-h-72 overflow-auto">
          {journey.touched_subcaps.map((t) => (
            <li key={t.sub_cap_id} className="py-2 text-xs">
              <div className="flex items-center gap-2 flex-wrap">
                <Link to={`/subcap?id=${encodeURIComponent(t.sub_cap_id)}`} className="font-mono text-[10px] text-zen-teal hover:text-zen-dark-teal">
                  {t.sub_cap_id}
                </Link>
                {t.state && (
                  <span className={`text-[10px] uppercase rounded px-1 ${STATE_BADGE[t.state] || ''}`}>
                    {t.state}
                  </span>
                )}
                <span className="text-zen-dark-green">{t.sub_cap_name}</span>
                <span className="ml-auto text-[10px] text-zen-dark-teal/70">{t.sow_count} SOW</span>
              </div>
              {t.sow_excerpts.length > 0 && (
                <div className="mt-1 italic text-[10px] text-zen-dark-teal bg-zen-white-green/60 rounded px-2 py-1">
                  “{t.sow_excerpts[0]}”
                </div>
              )}
            </li>
          ))}
        </ul>
      </div>

      <div className="bg-white rounded-lg border border-zen-light-green/40 p-3">
        <h3 className="text-xs uppercase font-semibold tracking-wider text-zen-dark-green mb-2 flex items-center gap-1">
          <Sparkles size={12} /> Vendor stack
        </h3>
        {journey.vendor_stack.length === 0 ? (
          <div className="text-xs text-zen-dark-teal/60 italic">No technographic data for this client.</div>
        ) : (
          <ul className="grid grid-cols-1 md:grid-cols-2 gap-1 text-xs">
            {journey.vendor_stack.map((v, i) => (
              <li key={i} className="flex items-center gap-2 text-zen-dark-teal">
                <span className="text-zen-dark-green font-medium">{v.vendor}</span>
                {v.category && (
                  <span className="text-[10px] uppercase rounded px-1 bg-zen-light-green/40 text-zen-dark-teal">{v.category}</span>
                )}
                <span className="text-[10px] text-zen-dark-teal/60">{(v.confidence * 100).toFixed(0)}%</span>
                <span className="ml-auto text-[10px] text-zen-dark-teal/60">
                  {v.cohort_adoption.length > 0 && `peer adoption ${Math.max(...v.cohort_adoption.map((a) => a.adoption_pct)).toFixed(0)}%`}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function KPI({ label, value }: { label: string; value: number }) {
  return (
    <div className="bg-zen-white-green/50 rounded p-2 text-center">
      <div className="text-2xl font-semibold text-zen-dark-green">{value}</div>
      <div className="text-[10px] uppercase tracking-wider text-zen-dark-teal/70">{label}</div>
    </div>
  );
}
