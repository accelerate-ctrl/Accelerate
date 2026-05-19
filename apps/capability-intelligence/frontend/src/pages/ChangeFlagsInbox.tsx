import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Loader2,
  ThumbsDown,
  ThumbsUp,
  X,
} from 'lucide-react';
import {
  apiGet,
  apiPost,
  type ChangeFlag,
  type FlagKindsSummary,
} from '@/lib/api';

const SEVERITY_STYLES: Record<string, string> = {
  LOW: 'bg-zen-light-green/60 text-zen-dark-green',
  MEDIUM: 'bg-zen-light-orange text-zen-dark-green',
  HIGH: 'bg-zen-orange text-white',
  BLOCKING: 'bg-zen-dark-green text-white',
};

const SEVERITIES = ['HIGH', 'MEDIUM', 'LOW', 'BLOCKING'] as const;

/**
 * Change Flags Inbox — App Flow J5.
 *
 * Triages catalogue regressions, AI-proposed edges, schema gaps, ingest
 * failures, and drift signals. Each flag carries one of three
 * dispositions:
 *
 *   - Approve  → resolves the flag as accepted.
 *   - Reject   → resolves as declined; requires a non-empty reason.
 *   - Defer    → keeps the flag open with a recheck cooldown.
 */
export default function ChangeFlagsInbox() {
  const qc = useQueryClient();
  const [openOnly, setOpenOnly] = useState(true);
  const [severity, setSeverity] = useState<string | null>(null);
  const [kindFilter, setKindFilter] = useState<string | null>(null);
  const [rejectFor, setRejectFor] = useState<ChangeFlag | null>(null);

  const summary = useQuery<FlagKindsSummary>({
    queryKey: ['flags-summary'],
    queryFn: () => apiGet<FlagKindsSummary>('/flags/_kinds'),
  });

  const list = useQuery<ChangeFlag[]>({
    queryKey: ['flags', openOnly, severity, kindFilter],
    queryFn: () => {
      const qs = new URLSearchParams({ open_only: String(openOnly) });
      if (severity) qs.set('severity', severity);
      if (kindFilter) qs.set('kind', kindFilter);
      return apiGet<ChangeFlag[]>(`/flags?${qs.toString()}`);
    },
  });

  const approve = useMutation({
    mutationFn: (id: string) => apiPost(`/flags/${id}/approve`, { note: null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['flags'] });
      qc.invalidateQueries({ queryKey: ['flags-summary'] });
    },
  });

  const defer = useMutation({
    mutationFn: (id: string) => apiPost(`/flags/${id}/defer`, { note: null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['flags'] });
      qc.invalidateQueries({ queryKey: ['flags-summary'] });
    },
  });

  const reject = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      apiPost(`/flags/${id}/reject`, { reason }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['flags'] });
      qc.invalidateQueries({ queryKey: ['flags-summary'] });
      setRejectFor(null);
    },
  });

  const rows = list.data ?? [];
  const kindEntries = Object.entries(summary.data?.kinds ?? {}).sort(
    (a, b) => b[1] - a[1],
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold text-fg">Change Flags Inbox</h1>
          <p className="text-sm text-fg-soft">
            Mapping regressions, AI-proposed edges, schema-incomplete pillars,
            ingest failures, and drift. Approve, reject (with reason), or defer
            each flag.
          </p>
        </div>
        <label className="text-xs text-fg-soft flex items-center gap-1">
          <input
            type="checkbox"
            checked={openOnly}
            onChange={(e) => setOpenOnly(e.target.checked)}
          />
          Open only
        </label>
      </div>

      {/* Filter chips */}
      <div className="flex flex-wrap items-center gap-2 bg-surface-overlay rounded-lg border border-border p-2">
        <span className="text-[10px] uppercase tracking-wider text-fg-muted">
          Severity
        </span>
        {SEVERITIES.map((s) => {
          const count = summary.data?.severities[s] ?? 0;
          if (count === 0 && severity !== s) return null;
          const active = severity === s;
          return (
            <button
              key={s}
              type="button"
              onClick={() => setSeverity(active ? null : s)}
              className={`text-[10px] uppercase tracking-wider rounded px-1.5 py-0.5 transition ${
                active
                  ? SEVERITY_STYLES[s]
                  : 'bg-surface text-fg-soft hover:bg-surface-raised'
              }`}
            >
              {s} {count > 0 && `(${count})`}
            </button>
          );
        })}
        {kindEntries.length > 0 && (
          <span className="text-[10px] uppercase tracking-wider text-fg-muted ml-2">
            Kind
          </span>
        )}
        {kindEntries.slice(0, 6).map(([k, n]) => {
          const active = kindFilter === k;
          return (
            <button
              key={k}
              type="button"
              onClick={() => setKindFilter(active ? null : k)}
              className={`text-[10px] font-mono rounded px-1.5 py-0.5 transition ${
                active
                  ? 'bg-accent text-fg-inverse'
                  : 'bg-surface text-fg-soft hover:bg-surface-raised'
              }`}
            >
              {k} ({n})
            </button>
          );
        })}
        {(severity || kindFilter) && (
          <button
            type="button"
            onClick={() => {
              setSeverity(null);
              setKindFilter(null);
            }}
            className="text-xs text-fg-soft hover:text-fg underline ml-auto"
          >
            Reset
          </button>
        )}
      </div>

      {list.isLoading && (
        <div className="text-xs text-fg-soft flex items-center gap-2">
          <Loader2 size={12} className="animate-spin" />
          Loading…
        </div>
      )}

      {!list.isLoading && rows.length === 0 && (
        <div className="bg-surface-overlay rounded-lg border border-border p-6 text-center text-sm text-fg-soft flex items-center justify-center gap-2">
          <CheckCircle2 size={16} className="text-zen-teal" /> No{' '}
          {openOnly ? 'open' : ''} flags
          {severity && ` at ${severity} severity`}
          {kindFilter && ` of kind ${kindFilter}`}.
        </div>
      )}

      {rows.length > 0 && (
        <div className="bg-surface-overlay rounded-lg border border-border divide-y divide-border">
          {rows.map((f) => (
            <FlagRow
              key={f.flag_id}
              flag={f}
              onApprove={() => approve.mutate(f.flag_id)}
              onDefer={() => defer.mutate(f.flag_id)}
              onReject={() => setRejectFor(f)}
              busy={
                approve.isPending && approve.variables === f.flag_id ||
                defer.isPending && defer.variables === f.flag_id
              }
            />
          ))}
        </div>
      )}

      {rejectFor && (
        <RejectModal
          flag={rejectFor}
          submitting={reject.isPending}
          onCancel={() => setRejectFor(null)}
          onSubmit={(reason) => reject.mutate({ id: rejectFor.flag_id, reason })}
        />
      )}
    </div>
  );
}

function FlagRow({
  flag,
  onApprove,
  onReject,
  onDefer,
  busy,
}: {
  flag: ChangeFlag;
  onApprove: () => void;
  onReject: () => void;
  onDefer: () => void;
  busy: boolean;
}) {
  const isResolved = !!flag.resolved_at;
  return (
    <div className="p-3 flex items-start gap-3">
      <AlertTriangle size={16} className="text-zen-orange shrink-0 mt-0.5" />
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span
            className={`text-[10px] uppercase tracking-wider rounded px-1.5 py-0.5 ${
              SEVERITY_STYLES[flag.severity] ?? ''
            }`}
          >
            {flag.severity}
          </span>
          <span className="text-fg-soft font-mono">{flag.kind}</span>
          <span className="text-fg-soft">·</span>
          <span className="text-fg">
            {flag.target_type}: <span className="font-mono">{flag.target_id}</span>
          </span>
          {flag.disposition && (
            <span className="ml-auto text-[10px] bg-surface text-fg-soft rounded px-1.5 py-0.5">
              {flag.disposition}
            </span>
          )}
        </div>
        <div className="text-sm text-fg font-medium mt-1">{flag.title}</div>
        <div className="text-xs text-fg-soft mt-0.5 whitespace-pre-line">
          {flag.detail}
        </div>
        <div className="text-[10px] text-fg-muted mt-1">
          detected {new Date(flag.detected_at).toLocaleString()}
          {flag.resolved_at &&
            ` · ${flag.disposition ?? 'resolved'} ${new Date(
              flag.resolved_at,
            ).toLocaleString()} by ${flag.resolved_by}`}
          {flag.deferred_until && !flag.resolved_at &&
            ` · deferred ${new Date(flag.deferred_until).toLocaleString()}`}
          {flag.disposition_note && ` · "${flag.disposition_note}"`}
        </div>
      </div>
      {!isResolved && (
        <div className="flex flex-col sm:flex-row gap-1 shrink-0">
          <button
            type="button"
            onClick={onApprove}
            disabled={busy}
            aria-label="approve flag"
            className="text-xs bg-accent text-fg-inverse rounded px-2 py-1 hover:opacity-90 disabled:opacity-50 flex items-center gap-1"
          >
            {busy ? <Loader2 size={10} className="animate-spin" /> : <ThumbsUp size={10} />}
            Approve
          </button>
          <button
            type="button"
            onClick={onDefer}
            disabled={busy}
            aria-label="defer flag"
            className="text-xs bg-surface text-fg border border-border rounded px-2 py-1 hover:bg-surface-raised disabled:opacity-50 flex items-center gap-1"
          >
            <Clock size={10} />
            Defer
          </button>
          <button
            type="button"
            onClick={onReject}
            disabled={busy}
            aria-label="reject flag"
            className="text-xs bg-warning text-fg-inverse rounded px-2 py-1 hover:opacity-90 disabled:opacity-50 flex items-center gap-1"
          >
            <ThumbsDown size={10} />
            Reject
          </button>
        </div>
      )}
    </div>
  );
}

function RejectModal({
  flag,
  submitting,
  onCancel,
  onSubmit,
}: {
  flag: ChangeFlag;
  submitting: boolean;
  onCancel: () => void;
  onSubmit: (reason: string) => void;
}) {
  const [reason, setReason] = useState('');
  const canSubmit = reason.trim().length > 0 && !submitting;
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="reject-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-zen-dark-green/60 p-4"
    >
      <div className="w-full max-w-md rounded-lg bg-surface-overlay border border-border shadow-lg">
        <div className="flex items-start justify-between gap-3 p-4 border-b border-border">
          <h2 id="reject-modal-title" className="text-base font-semibold text-fg">
            Reject flag
          </h2>
          <button
            type="button"
            onClick={onCancel}
            aria-label="close"
            className="text-fg-soft hover:text-fg"
          >
            <X size={16} />
          </button>
        </div>
        <div className="p-4 space-y-3">
          <div className="text-sm">
            <div className="text-fg font-medium">{flag.title}</div>
            <div className="text-xs text-fg-soft font-mono mt-0.5">{flag.kind}</div>
          </div>
          <label className="block text-sm">
            <span className="text-fg">
              Reason <span className="text-warning">(required)</span>
            </span>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              autoFocus
              placeholder="Why is this flag being rejected? The reason is recorded in the audit trail."
              className="mt-1 w-full rounded border border-border bg-surface px-2 py-1.5 text-sm text-fg focus:outline-none focus:ring-1 focus:ring-border-focus"
            />
          </label>
        </div>
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
            onClick={() => onSubmit(reason.trim())}
            disabled={!canSubmit}
            className="text-xs px-3 py-1.5 rounded bg-warning text-fg-inverse hover:opacity-90 disabled:opacity-50 flex items-center gap-1"
          >
            {submitting && <Loader2 size={10} className="animate-spin" />}
            Reject
          </button>
        </div>
      </div>
    </div>
  );
}
