import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, CheckCircle2 } from 'lucide-react';
import { apiGet, apiPost, type ChangeFlag } from '@/lib/api';

const SEVERITY_STYLES: Record<string, string> = {
  LOW: 'bg-zen-light-green/60 text-zen-dark-green',
  MEDIUM: 'bg-zen-light-orange text-zen-dark-green',
  HIGH: 'bg-zen-orange text-white',
  BLOCKING: 'bg-zen-dark-green text-white',
};

export default function ChangeFlagsInbox() {
  const qc = useQueryClient();
  const [openOnly, setOpenOnly] = useState(true);
  const { data, isLoading } = useQuery<ChangeFlag[]>({
    queryKey: ['flags', openOnly],
    queryFn: () => apiGet<ChangeFlag[]>(`/flags?open_only=${openOnly}`),
  });

  const resolve = useMutation({
    mutationFn: (id: string) => apiPost(`/flags/${id}/resolve`, { note: 'resolved from inbox' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['flags'] }),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zen-dark-green">Change Flags Inbox</h1>
          <p className="text-sm text-zen-dark-teal/80">
            Mapping regressions, theme alignment, schema-incomplete pillars, ingest failures, drift.
          </p>
        </div>
        <label className="text-xs text-zen-dark-teal flex items-center gap-1">
          <input type="checkbox" checked={openOnly} onChange={(e) => setOpenOnly(e.target.checked)} />
          Open only
        </label>
      </div>

      {isLoading && <div className="text-xs text-zen-dark-teal/60">Loading…</div>}

      {data && data.length === 0 && (
        <div className="bg-white rounded-lg border border-zen-light-green/40 p-6 text-center text-sm text-zen-dark-teal/70 flex items-center justify-center gap-2">
          <CheckCircle2 size={16} className="text-zen-teal" /> No {openOnly ? 'open' : ''} flags. Catalogue is clean.
        </div>
      )}

      {data && data.length > 0 && (
        <div className="bg-white rounded-lg shadow-sm border border-zen-light-green/40 divide-y divide-zen-light-green/30">
          {data.map((f) => (
            <div key={f.flag_id} className="p-3 flex items-start gap-3">
              <AlertTriangle size={16} className="text-zen-orange shrink-0 mt-0.5" />
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <span className={`text-[10px] uppercase tracking-wider rounded px-1.5 py-0.5 ${SEVERITY_STYLES[f.severity]}`}>
                    {f.severity}
                  </span>
                  <span className="text-zen-dark-teal/70 font-mono">{f.kind}</span>
                  <span className="text-zen-dark-teal">·</span>
                  <span className="text-zen-dark-green">
                    {f.target_type}: <span className="font-mono">{f.target_id}</span>
                  </span>
                </div>
                <div className="text-sm text-zen-dark-green font-medium mt-1">{f.title}</div>
                <div className="text-xs text-zen-dark-teal mt-0.5 whitespace-pre-line">{f.detail}</div>
                <div className="text-[10px] text-zen-dark-teal/60 mt-1">
                  detected {new Date(f.detected_at).toLocaleString()}
                  {f.resolved_at && ` · resolved ${new Date(f.resolved_at).toLocaleString()} by ${f.resolved_by}`}
                </div>
              </div>
              {!f.resolved_at && (
                <button
                  type="button"
                  onClick={() => resolve.mutate(f.flag_id)}
                  className="text-xs text-zen-teal hover:text-zen-dark-teal underline shrink-0"
                >
                  Resolve
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
