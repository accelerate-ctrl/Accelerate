import { AlertTriangle, Loader2, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { apiGet, apiPost } from '@/lib/api';

type TargetImpact = {
  label: string;
  collection: string;
  count: number;
  sample_ids: string[];
};

type CascadeReport = {
  sub_cap_id: string;
  sub_cap_name: string;
  from_status: string | null;
  to_status: string;
  reason: string | null;
  targets: TargetImpact[];
  total_rows_affected: number;
  applied: boolean;
  run_id: string | null;
};

type Props = {
  subCapId: string;
  toStatus?: 'Inactive' | 'Active';
  onCancel: () => void;
  onApplied?: (report: CascadeReport) => void;
};

/**
 * Cascade preview modal — implements App Flow J4.
 *
 * Loads the preview synchronously on mount, surfaces every affected
 * downstream collection with row counts and sample IDs, and demands an
 * explicit reason before allowing the user to commit. The submit button
 * stays disabled until both the preview has loaded and a non-empty
 * reason has been entered.
 */
export default function CascadePreviewModal({
  subCapId,
  toStatus = 'Inactive',
  onCancel,
  onApplied,
}: Props) {
  const [report, setReport] = useState<CascadeReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState('');
  const [applying, setApplying] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    apiGet<CascadeReport>(
      `/cascade/preview/${encodeURIComponent(subCapId)}?to_status=${encodeURIComponent(toStatus)}`,
    )
      .then((r) => {
        if (!cancelled) setReport(r);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [subCapId, toStatus]);

  async function commit() {
    if (!reason.trim()) return;
    setApplying(true);
    setError(null);
    try {
      const r = await apiPost<CascadeReport>(
        `/cascade/apply/${encodeURIComponent(subCapId)}`,
        { to_status: toStatus, reason: reason.trim() },
      );
      onApplied?.(r);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setApplying(false);
    }
  }

  const canCommit = !!report && reason.trim().length > 0 && !applying;
  const verb = toStatus === 'Inactive' ? 'Deactivate' : 'Reactivate';

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="cascade-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-zen-dark-green/60 p-4"
    >
      <div className="w-full max-w-2xl rounded-lg bg-surface-overlay shadow-lg border border-border max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-start justify-between gap-3 p-4 border-b border-border">
          <div className="flex items-start gap-2">
            <AlertTriangle size={18} className="mt-0.5 text-warning" />
            <div>
              <h2 id="cascade-modal-title" className="text-base font-semibold text-fg">
                {verb} {subCapId}
              </h2>
              <p className="text-xs text-fg-soft mt-0.5">
                This change cascades across every dependent row. Review
                the impact below before committing.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onCancel}
            aria-label="close"
            className="text-fg-soft hover:text-fg p-1"
          >
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-auto p-4 space-y-4">
          {loading && (
            <div className="flex items-center gap-2 text-sm text-fg-soft">
              <Loader2 size={14} className="animate-spin" />
              Loading cascade preview…
            </div>
          )}
          {error && (
            <div className="text-sm text-warning bg-warning/10 rounded p-2 border border-warning/30">
              {error}
            </div>
          )}
          {report && (
            <>
              <div className="text-sm text-fg">
                <span className="font-medium">{report.sub_cap_name}</span>
                {' · '}
                <span className="text-fg-soft">
                  {report.from_status ?? 'unset'} → {report.to_status}
                </span>
              </div>

              <div className="rounded border border-border">
                <div className="flex items-center justify-between p-2 bg-surface">
                  <span className="text-sm font-medium text-fg">Downstream impact</span>
                  <span className="text-sm font-semibold text-fg">
                    {report.total_rows_affected} rows
                  </span>
                </div>
                {report.targets.length === 0 ? (
                  <div className="p-3 text-xs text-fg-muted">
                    No downstream rows reference this subcap.
                  </div>
                ) : (
                  <ul className="divide-y divide-border">
                    {report.targets.map((t) => (
                      <li key={t.collection} className="p-2 text-xs">
                        <div className="flex items-center justify-between">
                          <span className="text-fg">{t.label}</span>
                          <span className="font-mono text-fg-soft">{t.count}</span>
                        </div>
                        {t.sample_ids.length > 0 && (
                          <div className="mt-1 text-fg-muted truncate">
                            e.g. {t.sample_ids.slice(0, 3).join(', ')}
                          </div>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <label className="block text-sm">
                <span className="text-fg">
                  Reason <span className="text-warning">(required)</span>
                </span>
                <textarea
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  rows={3}
                  placeholder="Why is this subcap being toggled?"
                  className="mt-1 w-full rounded border border-border bg-surface px-2 py-1.5 text-sm text-fg focus:outline-none focus:ring-1 focus:ring-border-focus"
                />
              </label>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 p-3 border-t border-border bg-surface">
          <button
            type="button"
            onClick={onCancel}
            className="text-xs px-3 py-1.5 rounded border border-border text-fg hover:bg-surface-raised"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={commit}
            disabled={!canCommit}
            className="text-xs px-3 py-1.5 rounded bg-warning text-fg-inverse hover:opacity-90 disabled:opacity-50 flex items-center gap-1"
          >
            {applying && <Loader2 size={12} className="animate-spin" />}
            {verb}
          </button>
        </div>
      </div>
    </div>
  );
}
