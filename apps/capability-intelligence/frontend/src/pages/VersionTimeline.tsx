import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  GitCommit,
  Loader2,
  RotateCcw,
  Save,
  X,
} from 'lucide-react';
import { apiGet, apiPost, type CatalogueVersion } from '@/lib/api';

type RevertPreview = {
  target_version_id: string;
  target_label?: string | null;
  target_created_at?: string | null;
  target_created_by?: string | null;
  current_subcap_count: number;
  target_subcap_count: number;
  added_subcaps: string[];
  removed_subcaps: string[];
  modified_subcaps: Array<{ sub_cap_id: string }>;
  pillar_count_deltas: Record<string, number>;
};

export default function VersionTimeline() {
  const qc = useQueryClient();
  const [label, setLabel] = useState('');
  const [summary, setSummary] = useState('');
  const [revertTarget, setRevertTarget] = useState<CatalogueVersion | null>(null);

  const { data: versions } = useQuery<CatalogueVersion[]>({
    queryKey: ['versions'],
    queryFn: () => apiGet<CatalogueVersion[]>('/versions'),
  });

  const save = useMutation({
    mutationFn: () => apiPost<CatalogueVersion>('/versions', { label, summary }),
    onSuccess: () => {
      setLabel('');
      setSummary('');
      qc.invalidateQueries({ queryKey: ['versions'] });
    },
  });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-zen-dark-green">Version Timeline</h1>
        <p className="text-sm text-zen-dark-teal/80">
          Every save is a snapshot; diffs and rollbacks reference these IDs.
          Reverts are admin-gated (App Flow J11) and emit a new version entry
          so the timeline preserves the operator action.
        </p>
      </div>

      <div className="bg-white rounded-lg shadow-sm border border-zen-light-green/40 p-3">
        <h2 className="text-xs font-semibold text-zen-dark-green uppercase tracking-wider mb-2">
          Save current state as a new version
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Label (optional)"
            className="border border-zen-light-green rounded px-2 py-1 text-sm flex-1 min-w-[180px]"
          />
          <input
            type="text"
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            placeholder="One-line summary (optional)"
            className="border border-zen-light-green rounded px-2 py-1 text-sm flex-[2] min-w-[260px]"
          />
          <button
            type="button"
            onClick={() => save.mutate()}
            disabled={save.isPending}
            className="bg-zen-teal hover:bg-zen-dark-teal text-white text-sm px-3 py-1.5 rounded disabled:opacity-50"
          >
            <Save size={14} className="inline mr-1" /> Save version
          </button>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow-sm border border-zen-light-green/40 p-3">
        <h2 className="text-xs font-semibold text-zen-dark-green uppercase tracking-wider mb-2">History</h2>
        {!versions || versions.length === 0 ? (
          <div className="text-xs text-zen-dark-teal/70">No versions saved yet.</div>
        ) : (
          <ul className="divide-y divide-zen-light-green/30">
            {versions.map((v) => (
              <li key={v.version_id} className="py-2 flex items-start gap-2">
                <GitCommit
                  size={16}
                  className={v.is_current ? 'text-zen-teal mt-0.5' : 'text-zen-dark-teal/50 mt-0.5'}
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 text-sm">
                    <span className="font-mono text-xs text-zen-dark-teal">{v.version_id}</span>
                    {v.is_current && (
                      <span className="text-[10px] uppercase bg-zen-teal/30 text-zen-dark-green rounded px-1.5 py-0.5">
                        current
                      </span>
                    )}
                    {(v as unknown as { is_revert?: boolean }).is_revert && (
                      <span className="text-[10px] uppercase bg-zen-light-orange text-zen-dark-green rounded px-1.5 py-0.5">
                        revert
                      </span>
                    )}
                    {v.label && <span className="text-zen-dark-green font-medium">{v.label}</span>}
                  </div>
                  <div className="text-xs text-zen-dark-teal/80 mt-0.5">{v.summary}</div>
                  <div className="text-[10px] text-zen-dark-teal/60 mt-0.5">
                    {new Date(v.created_at).toLocaleString()} · by {v.created_by} · pillar counts:{' '}
                    {Object.entries(v.pillar_counts)
                      .map(([k, n]) => `${k}=${n}`)
                      .join(', ')}
                  </div>
                </div>
                <div className="flex flex-col gap-1 shrink-0">
                  <Link
                    to={`/diff?b=${v.version_id}`}
                    className="text-xs text-zen-teal hover:text-zen-dark-teal underline text-right"
                  >
                    Diff →
                  </Link>
                  {!v.is_current && (
                    <button
                      type="button"
                      onClick={() => setRevertTarget(v)}
                      aria-label={`revert to ${v.version_id}`}
                      className="text-xs text-zen-orange hover:text-zen-dark-green underline text-right inline-flex items-center justify-end gap-1"
                    >
                      <RotateCcw size={10} /> Revert
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {revertTarget && (
        <RevertModal
          target={revertTarget}
          onClose={() => setRevertTarget(null)}
          onSuccess={() => {
            setRevertTarget(null);
            qc.invalidateQueries({ queryKey: ['versions'] });
          }}
        />
      )}
    </div>
  );
}

/**
 * J11 revert modal — admin-gated at the API edge. Loads the
 * revert-preview synchronously so the operator sees exactly what will
 * change before they commit. Reason is required for the audit trail.
 */
function RevertModal({
  target,
  onClose,
  onSuccess,
}: {
  target: CatalogueVersion;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [reason, setReason] = useState('');
  const { data: preview, isLoading, error } = useQuery<RevertPreview>({
    queryKey: ['revert-preview', target.version_id],
    queryFn: () =>
      apiGet<RevertPreview>(
        `/versions/${encodeURIComponent(target.version_id)}/revert-preview`,
      ),
  });
  const revert = useMutation({
    mutationFn: () =>
      apiPost(
        `/versions/${encodeURIComponent(target.version_id)}/revert`,
        { reason: reason.trim() },
      ),
    onSuccess,
  });
  const canCommit =
    !!preview && reason.trim().length > 0 && !revert.isPending;
  const errorMsg = error || revert.error;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="revert-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-zen-dark-green/60 p-4"
    >
      <div className="w-full max-w-2xl rounded-lg bg-white border border-zen-separator shadow-lg max-h-[90vh] overflow-hidden flex flex-col">
        <div className="flex items-start justify-between gap-3 p-4 border-b border-zen-separator">
          <div className="flex items-start gap-2">
            <AlertTriangle size={18} className="mt-0.5 text-zen-orange" />
            <div>
              <h2 id="revert-modal-title" className="text-base font-semibold text-zen-dark-green">
                Revert catalogue to {target.version_id}
              </h2>
              <p className="text-xs text-zen-dark-teal/80 mt-0.5">
                Admin-gated. A new version entry is created so the history
                preserves this revert action. Reason is recorded in the audit
                trail.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="close"
            className="text-zen-dark-teal/60 hover:text-zen-dark-green p-1"
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-auto p-4 space-y-3">
          {isLoading && (
            <div className="flex items-center gap-2 text-sm text-zen-dark-teal/80">
              <Loader2 size={14} className="animate-spin" />
              Loading revert preview…
            </div>
          )}
          {errorMsg && (
            <div className="text-sm text-zen-orange bg-zen-light-orange/40 border border-zen-orange/30 rounded p-2">
              {errorMsg instanceof Error ? errorMsg.message : String(errorMsg)}
            </div>
          )}
          {preview && (
            <>
              <div className="text-sm text-zen-dark-green">
                Reverting to <strong>{preview.target_label || target.version_id}</strong>{' '}
                ({preview.target_created_at && new Date(preview.target_created_at).toLocaleDateString()})
              </div>
              <div className="grid grid-cols-3 gap-2 text-center text-sm">
                <Stat label="Added subcaps" n={preview.added_subcaps.length} tone="teal" />
                <Stat label="Removed subcaps" n={preview.removed_subcaps.length} tone="orange" />
                <Stat label="Modified subcaps" n={preview.modified_subcaps.length} tone="muted" />
              </div>
              <details className="text-xs text-zen-dark-teal">
                <summary className="cursor-pointer text-zen-teal hover:text-zen-dark-teal">
                  Show subcap ids
                </summary>
                <div className="mt-2 space-y-1 max-h-48 overflow-auto">
                  {preview.added_subcaps.length > 0 && (
                    <div>
                      <span className="text-zen-teal font-medium">+ </span>
                      <span className="font-mono">{preview.added_subcaps.join(', ')}</span>
                    </div>
                  )}
                  {preview.removed_subcaps.length > 0 && (
                    <div>
                      <span className="text-zen-orange font-medium">− </span>
                      <span className="font-mono">{preview.removed_subcaps.join(', ')}</span>
                    </div>
                  )}
                  {preview.modified_subcaps.length > 0 && (
                    <div>
                      <span className="text-zen-dark-teal font-medium">~ </span>
                      <span className="font-mono">
                        {preview.modified_subcaps.map((m) => m.sub_cap_id).join(', ')}
                      </span>
                    </div>
                  )}
                </div>
              </details>
              <label className="block text-sm">
                <span className="text-zen-dark-green">
                  Reason <span className="text-zen-orange">(required)</span>
                </span>
                <textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  rows={3}
                  autoFocus
                  placeholder="Why is the catalogue being reverted? Recorded in the audit trail."
                  className="mt-1 w-full rounded border border-zen-separator bg-white px-2 py-1.5 text-sm text-zen-dark-green focus:outline-none focus:ring-1 focus:ring-zen-teal"
                />
              </label>
            </>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 p-3 border-t border-zen-separator bg-zen-ice/50">
          <button
            type="button"
            onClick={onClose}
            className="text-xs px-3 py-1.5 rounded border border-zen-separator text-zen-dark-green hover:bg-zen-light-green/40"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => revert.mutate()}
            disabled={!canCommit}
            className="text-xs px-3 py-1.5 rounded bg-zen-orange text-white hover:opacity-90 disabled:opacity-50 inline-flex items-center gap-1"
          >
            {revert.isPending && <Loader2 size={10} className="animate-spin" />}
            <RotateCcw size={10} />
            Revert
          </button>
        </div>
      </div>
    </div>
  );
}

function Stat({
  label,
  n,
  tone,
}: {
  label: string;
  n: number;
  tone: 'teal' | 'orange' | 'muted';
}) {
  const bg =
    tone === 'teal'
      ? 'bg-zen-light-green/40 text-zen-dark-green'
      : tone === 'orange'
      ? 'bg-zen-light-orange/50 text-zen-dark-green'
      : 'bg-zen-ice text-zen-dark-teal';
  return (
    <div className={`rounded p-2 ${bg}`}>
      <div className="text-lg font-semibold">{n}</div>
      <div className="text-[10px] uppercase tracking-wider">{label}</div>
    </div>
  );
}
