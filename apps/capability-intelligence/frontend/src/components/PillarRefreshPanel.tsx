import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { RefreshCw, AlertTriangle, CheckCircle2, FileSpreadsheet } from 'lucide-react';
import { apiGet, apiPost, type DiscoveredFile, type IngestRun } from '@/lib/api';

type DiscoverResp = { pillars: DiscoveredFile[]; discovered_at: string };

export default function PillarRefreshPanel() {
  const qc = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);

  const { data, isLoading } = useQuery<DiscoverResp>({
    queryKey: ['discover'],
    queryFn: () => apiGet<DiscoverResp>('/sheets/discover'),
  });

  const refresh = useMutation({
    mutationFn: async (pillarId: string | 'ALL') => {
      const path = pillarId === 'ALL' ? '/sheets/refresh' : `/sheets/refresh/${pillarId}`;
      return apiPost<IngestRun>(path);
    },
    onSettled: () => {
      setBusy(null);
      qc.invalidateQueries();
    },
  });

  const onRefresh = (pid: string | 'ALL') => {
    setBusy(pid);
    refresh.mutate(pid);
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-zen-light-green/40 p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-zen-dark-green flex items-center gap-2">
          <FileSpreadsheet size={16} /> Pillar source files
        </h2>
        <button
          onClick={() => onRefresh('ALL')}
          disabled={refresh.isPending}
          className="text-xs bg-zen-teal hover:bg-zen-dark-teal text-white px-2.5 py-1 rounded transition-colors disabled:opacity-50"
        >
          <RefreshCw size={12} className={`inline mr-1 ${busy === 'ALL' ? 'animate-spin' : ''}`} />
          Refresh all
        </button>
      </div>

      {isLoading && <div className="text-xs text-zen-dark-teal/60">Discovering…</div>}

      {data && data.pillars.length === 0 && (
        <div className="text-xs text-zen-dark-teal/70 bg-zen-white-green/60 rounded p-3">
          No pillar files discovered. Confirm the Drive folder is shared with the service account
          (see Settings & INPUT_CHECKLIST.md).
        </div>
      )}

      <div className="space-y-1.5">
        {data?.pillars.map((p) => (
          <div
            key={p.pillar_id}
            className="flex items-center justify-between text-xs border border-zen-light-green/40 rounded px-2 py-1.5"
          >
            <div className="min-w-0 flex-1">
              <div className="font-medium text-zen-dark-green flex items-center gap-2">
                {p.pillar_id}
                {p.parsed_version ? (
                  <span className="bg-zen-light-green/60 text-zen-dark-teal rounded px-1.5 py-px text-[10px]">
                    {p.parsed_version}
                  </span>
                ) : (
                  <span className="bg-zen-light-orange/60 text-zen-dark-green rounded px-1.5 py-px text-[10px]">
                    no version tag
                  </span>
                )}
                <span className="text-zen-dark-teal/60 text-[10px]">{p.source}</span>
              </div>
              <div className="truncate text-zen-dark-teal/80">{p.file_name}</div>
            </div>
            <button
              onClick={() => onRefresh(p.pillar_id)}
              disabled={refresh.isPending}
              className="ml-2 text-zen-teal hover:text-zen-dark-teal disabled:opacity-50"
              aria-label={`refresh ${p.pillar_id}`}
              title={`Refresh ${p.pillar_id}`}
            >
              <RefreshCw size={14} className={busy === p.pillar_id ? 'animate-spin' : ''} />
            </button>
          </div>
        ))}
      </div>

      {refresh.data && (
        <div className="mt-3 text-xs">
          {refresh.data.pillars_loaded.length > 0 && (
            <div className="text-zen-dark-teal flex items-start gap-1.5">
              <CheckCircle2 size={14} className="text-zen-teal mt-0.5" />
              <div>
                Loaded: {refresh.data.pillars_loaded.join(', ')}
                {Object.entries(refresh.data.counts_by_pillar).map(([pid, counts]) => (
                  <div key={pid} className="text-zen-dark-teal/70">
                    {pid}: {counts.subcaps} subcaps · {counts.l3} L3 · {counts.l4} L4
                  </div>
                ))}
              </div>
            </div>
          )}
          {refresh.data.pillars_skipped.length > 0 && (
            <div className="text-zen-dark-green flex items-start gap-1.5 mt-1">
              <AlertTriangle size={14} className="text-zen-orange mt-0.5" />
              <div>
                Skipped:{' '}
                {refresh.data.pillars_skipped.map((s) => `${s.pillar_id} (${s.reason})`).join(', ')}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
