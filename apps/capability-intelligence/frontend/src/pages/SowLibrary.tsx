import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, FileText, RefreshCw, ShieldCheck } from 'lucide-react';
import { Link } from 'react-router-dom';
import { apiGet, apiPost, type Sow, type SowIngestRun, type SowPreview, type SowStatus } from '@/lib/api';

const STATUS_BADGE: Record<SowStatus, string> = {
  active: 'bg-zen-teal text-white',
  prospect: 'bg-zen-light-orange text-zen-dark-green',
  inactive: 'bg-zen-light-green/60 text-zen-dark-teal',
  archived: 'bg-zen-dark-teal/30 text-zen-dark-green',
};

export default function SowLibrary() {
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<SowStatus | ''>('');
  const [openSow, setOpenSow] = useState<string | null>(null);

  const { data: sows, isLoading } = useQuery<Sow[]>({
    queryKey: ['sows', statusFilter],
    queryFn: () => apiGet<Sow[]>(statusFilter ? `/sows?status=${statusFilter}` : '/sows'),
  });

  const refresh = useMutation({
    mutationFn: () => apiPost<SowIngestRun>('/sows/refresh'),
    onSettled: () => qc.invalidateQueries(),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zen-dark-green">SOW Library</h1>
          <p className="text-sm text-zen-dark-teal/80">
            Statements of Work pulled from Drive (or local <span className="font-mono">test-data/SOWs/</span>),
            DLP-redacted, chunked, and subcap-mention-tagged.
          </p>
        </div>
        <button
          type="button"
          onClick={() => refresh.mutate()}
          disabled={refresh.isPending}
          className="bg-zen-teal hover:bg-zen-dark-teal text-white text-xs font-medium px-3 py-1.5 rounded transition-colors disabled:opacity-50"
        >
          <RefreshCw size={12} className={`inline mr-1 ${refresh.isPending ? 'animate-spin' : ''}`} />
          Refresh ingest
        </button>
      </div>

      {refresh.data && (
        <div className="bg-white border border-zen-light-green/40 rounded-lg p-3 text-xs text-zen-dark-teal flex items-start gap-2">
          <CheckCircle2 size={14} className="text-zen-teal mt-0.5" />
          <div>
            Ingested <strong>{refresh.data.sows_loaded}</strong> SOWs · {refresh.data.chunks_total} chunks ·{' '}
            <strong>{refresh.data.mentions_total}</strong> subcap mentions ·{' '}
            <strong>{refresh.data.redactions_total}</strong> PII redactions
          </div>
        </div>
      )}

      <div className="bg-white rounded-lg border border-zen-light-green/40 p-2 flex items-center gap-2 text-xs">
        <span className="text-zen-dark-teal/70">Status</span>
        {(['', 'active', 'prospect', 'inactive', 'archived'] as const).map((s) => (
          <button
            key={s || 'all'}
            onClick={() => setStatusFilter(s as SowStatus | '')}
            className={`px-2 py-0.5 rounded ${
              statusFilter === s ? 'bg-zen-dark-green text-white' : 'bg-zen-light-green/40 text-zen-dark-teal/80'
            }`}
          >
            {s || 'all'}
          </button>
        ))}
      </div>

      {isLoading && <div className="text-xs text-zen-dark-teal/60">Loading…</div>}

      {sows && sows.length === 0 && (
        <div className="bg-white rounded-lg border border-zen-light-green/40 p-6 text-center text-sm text-zen-dark-teal/70">
          No SOWs ingested yet. Click <strong>Refresh ingest</strong> to scan the configured folder.
        </div>
      )}

      <div className="bg-white rounded-lg border border-zen-light-green/40 divide-y divide-zen-light-green/30">
        {sows?.map((sow) => {
          const totalRedactions = Object.values(sow.redaction_summary || {}).reduce((a, b) => a + b, 0);
          return (
            <div key={sow.sow_id} className="p-3">
              <div className="flex items-start gap-3">
                <FileText size={16} className="text-zen-dark-teal/60 mt-0.5 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`text-[10px] uppercase rounded px-1.5 py-0.5 ${STATUS_BADGE[sow.status]}`}>
                      {sow.status}
                    </span>
                    <span className="text-sm font-medium text-zen-dark-green">{sow.client_name}</span>
                    <span className="text-xs text-zen-dark-teal/70">·</span>
                    <span className="font-mono text-xs text-zen-dark-teal/80 truncate">{sow.file_name}</span>
                  </div>
                  <div className="text-[10px] text-zen-dark-teal/60 mt-0.5 flex flex-wrap gap-x-3">
                    <span>{sow.page_count} page · {sow.char_count.toLocaleString()} chars · {sow.chunk_count} chunks</span>
                    <span><strong>{sow.mention_count}</strong> subcap mentions</span>
                    <span className="inline-flex items-center gap-0.5">
                      <ShieldCheck size={10} className="text-zen-teal" />
                      {totalRedactions} redactions ({Object.entries(sow.redaction_summary || {}).map(([k, n]) => `${k}:${n}`).join(', ') || 'none'})
                    </span>
                  </div>
                </div>
                <button
                  onClick={() => setOpenSow(openSow === sow.sow_id ? null : sow.sow_id)}
                  className="text-xs text-zen-teal hover:text-zen-dark-teal underline"
                >
                  {openSow === sow.sow_id ? 'Hide preview' : 'Show preview'}
                </button>
              </div>
              {openSow === sow.sow_id && <SowPreviewPanel sowId={sow.sow_id} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SowPreviewPanel({ sowId }: { sowId: string }) {
  const { data, isLoading } = useQuery<SowPreview>({
    queryKey: ['sow-preview', sowId],
    queryFn: () => apiGet<SowPreview>(`/sows/${encodeURIComponent(sowId)}/preview`),
  });
  const { data: detail } = useQuery<{ sow: Sow; mentions: { sub_cap_id: string; method: string; excerpt: string }[] }>({
    queryKey: ['sow-detail', sowId],
    queryFn: () => apiGet(`/sows/${encodeURIComponent(sowId)}`),
  });
  return (
    <div className="mt-3 grid grid-cols-1 lg:grid-cols-2 gap-3 pl-7">
      <div className="bg-zen-white-green rounded p-2">
        <div className="text-[10px] uppercase text-zen-dark-teal/70 mb-1 flex items-center gap-1">
          <ShieldCheck size={10} className="text-zen-teal" /> Redacted preview
        </div>
        {isLoading && <div className="text-xs text-zen-dark-teal/60">Loading…</div>}
        {data && (
          <pre className="text-[10px] font-mono whitespace-pre-wrap text-zen-dark-teal max-h-72 overflow-auto">
{data.preview}
          </pre>
        )}
      </div>
      <div>
        <div className="text-[10px] uppercase text-zen-dark-teal/70 mb-1">Mentions</div>
        {!detail && <div className="text-xs text-zen-dark-teal/60">Loading…</div>}
        {detail && (
          <ul className="space-y-1 max-h-72 overflow-auto">
            {detail.mentions.length === 0 && <li className="text-xs text-zen-dark-teal/60 italic">no mentions</li>}
            {detail.mentions.map((m, i) => (
              <li key={i} className="text-xs">
                <Link
                  to={`/subcap?id=${encodeURIComponent(m.sub_cap_id)}`}
                  className="font-mono text-zen-teal hover:text-zen-dark-teal mr-2"
                >
                  {m.sub_cap_id}
                </Link>
                <span className="text-[10px] text-zen-dark-teal/60 mr-1">[{m.method}]</span>
                <span className="text-zen-dark-teal">{m.excerpt}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
