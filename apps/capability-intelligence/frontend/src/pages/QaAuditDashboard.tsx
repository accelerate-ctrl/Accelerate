import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  CheckCircle2,
  Check,
  Info,
  Play,
  ShieldAlert,
  Trash2,
  XCircle,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import {
  apiGet,
  apiPost,
  type AuditFinding,
  type AuditReport,
  type Suggestion,
} from '@/lib/api';
import ReasoningChainMini, { type ChainSummary } from '@/components/ReasoningChainMini';

const SEVERITY_BADGE: Record<string, string> = {
  critical: 'bg-zen-orange text-white',
  warn: 'bg-zen-light-orange text-zen-dark-green',
  info: 'bg-zen-light-green/60 text-zen-dark-teal',
};

function SevIcon({ s }: { s: string }) {
  if (s === 'critical') return <XCircle size={12} className="text-zen-orange" />;
  if (s === 'warn') return <AlertTriangle size={12} className="text-zen-orange" />;
  return <Info size={12} className="text-zen-teal" />;
}

export default function QaAuditDashboard() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<'all' | 'critical' | 'warn' | 'info'>('all');

  const { data: reports } = useQuery<AuditReport[]>({
    queryKey: ['audit-reports'],
    queryFn: () => apiGet<AuditReport[]>('/audit?limit=20'),
  });

  const { data: pendingSuggestions } = useQuery<Suggestion[]>({
    queryKey: ['suggestions', 'pending'],
    queryFn: () => apiGet<Suggestion[]>('/suggestions?status=pending'),
  });

  const latest = reports && reports[0];

  const run = useMutation({
    mutationFn: () => apiPost<AuditReport>('/audit/run'),
    onSettled: () => qc.invalidateQueries(),
  });

  const apply = useMutation({
    mutationFn: (sid: string) => apiPost(`/suggestions/${sid}/apply`, {}),
    onSettled: () => qc.invalidateQueries(),
  });
  const reject = useMutation({
    mutationFn: (sid: string) =>
      apiPost(`/suggestions/${sid}/reject`, { reason: 'rejected via QA dashboard' }),
    onSettled: () => qc.invalidateQueries(),
  });

  const visibleFindings: AuditFinding[] = (latest?.findings || []).filter(
    (f) => filter === 'all' || f.severity === filter,
  );

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-2xl font-semibold text-zen-dark-green">QA & Audit</h1>
          <p className="text-sm text-zen-dark-teal/80 max-w-3xl">
            Cross-source signal feed (gates, suggestions, flags, lifecycle, cost) on the left.
            Pending AI-proposed changes on the right — each card includes the adversarial
            self-review and a compact reasoning-chain widget so you can approve or send back
            without leaving the page.
          </p>
        </div>
        <button
          onClick={() => run.mutate()}
          disabled={run.isPending}
          className="bg-zen-teal hover:bg-zen-dark-teal text-white text-xs font-medium px-3 py-1.5 rounded transition-colors disabled:opacity-50"
        >
          <Play size={12} className={`inline mr-1 ${run.isPending ? 'animate-pulse' : ''}`} />
          Run audit
        </button>
      </div>

      {latest && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <KPI label="Findings" value={latest.findings.length} icon={<ShieldAlert size={12} />} />
          <KPI label="Critical" value={latest.summary.critical} tone="critical" />
          <KPI label="Warn" value={latest.summary.warn} tone="warn" />
          <KPI label="Info" value={latest.summary.info} tone="info" />
          <KPI label="Pending suggestions" value={pendingSuggestions?.length ?? 0} tone="info" />
        </div>
      )}

      {!latest && (
        <div className="bg-white rounded-lg border border-zen-separator p-6 text-center text-sm text-zen-text-gray">
          No audits yet — click <strong>Run audit</strong>.
        </div>
      )}

      {/* Two-pane: signal feed (left) + proposed changes queue (right) */}
      {latest && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {/* Left: signal feed */}
          <div className="bg-white rounded-lg border border-zen-separator p-3 max-h-[720px] overflow-auto">
            <div className="flex items-center gap-2 text-xs text-zen-text-gray mb-2 sticky top-0 bg-white pb-2 border-b border-zen-separator">
              <CheckCircle2 size={14} className="text-zen-teal" />
              <span>
                Signal feed · <strong className="font-mono text-zen-dark-green">{latest.report_id}</strong>
              </span>
              <span>· {new Date(latest.started_at).toLocaleString()}</span>
              <div className="ml-auto flex gap-1">
                {(['all', 'critical', 'warn', 'info'] as const).map((f) => (
                  <button
                    key={f}
                    onClick={() => setFilter(f)}
                    className={`text-[10px] uppercase rounded px-1.5 py-0.5 ${
                      filter === f
                        ? 'bg-zen-dark-green text-white'
                        : 'bg-zen-ice text-zen-text-gray'
                    }`}
                  >
                    {f}
                  </button>
                ))}
              </div>
            </div>
            <ul className="divide-y divide-zen-separator/40">
              {visibleFindings.length === 0 && (
                <li className="text-xs text-zen-muted-text italic py-2">
                  No findings for this severity filter.
                </li>
              )}
              {visibleFindings.map((f, i) => (
                <li key={i} className="py-2 text-xs">
                  <div className="flex items-center gap-2 flex-wrap">
                    <SevIcon s={f.severity} />
                    <span className={`uppercase rounded px-1 ${SEVERITY_BADGE[f.severity]}`}>
                      {f.severity}
                    </span>
                    <span className="font-mono text-[10px] text-zen-muted-text">{f.kind}</span>
                    <span className="text-zen-dark-green font-medium flex-1">{f.title}</span>
                    {f.ref_collection === 'reasoning_chains' && f.ref_id && (
                      <Link
                        to={`/reasoning?id=${encodeURIComponent(f.ref_id)}`}
                        className="text-[10px] text-zen-teal hover:text-zen-dark-teal underline"
                      >
                        view chain
                      </Link>
                    )}
                    {f.ref_collection === 'suggestions' && f.ref_id && (
                      <Link
                        to="/suggestions"
                        className="text-[10px] text-zen-teal hover:text-zen-dark-teal underline"
                      >
                        view suggestion
                      </Link>
                    )}
                    {f.ref_collection === 'lifecycle_scores' && f.ref_id && (
                      <Link
                        to={`/subcap?id=${encodeURIComponent(f.ref_id)}`}
                        className="text-[10px] text-zen-teal hover:text-zen-dark-teal underline"
                      >
                        view subcap
                      </Link>
                    )}
                  </div>
                  <div className="text-[11px] text-zen-text-gray mt-0.5">{f.detail}</div>
                </li>
              ))}
            </ul>
          </div>

          {/* Right: pending suggestions review queue */}
          <div className="bg-white rounded-lg border border-zen-separator p-3 max-h-[720px] overflow-auto">
            <div className="flex items-center gap-2 text-xs text-zen-text-gray mb-2 sticky top-0 bg-white pb-2 border-b border-zen-separator">
              <strong className="text-zen-dark-green">Proposed changes</strong>
              <span>· {pendingSuggestions?.length ?? 0} pending</span>
              <Link to="/suggestions" className="ml-auto text-[10px] text-zen-teal hover:text-zen-dark-teal underline">
                Full suggestions board →
              </Link>
            </div>
            {!pendingSuggestions || pendingSuggestions.length === 0 ? (
              <div className="text-xs text-zen-muted-text italic py-2">
                No pending AI-proposed changes. As the consultant loop runs (chat, news impact
                synth, partner releases), proposed edits will surface here for approval.
              </div>
            ) : (
              <ul className="space-y-3">
                {pendingSuggestions.slice(0, 12).map((s) => (
                  <ReviewRow
                    key={s.id}
                    s={s}
                    onApply={() => apply.mutate(s.id)}
                    onReject={() => reject.mutate(s.id)}
                  />
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {(reports || []).length > 1 && (
        <div className="bg-white rounded-lg border border-zen-separator p-3">
          <h2 className="text-xs uppercase font-semibold tracking-wider text-zen-dark-green mb-2">
            History
          </h2>
          <ul className="divide-y divide-zen-separator/40">
            {(reports || []).slice(1).map((r) => (
              <li key={r.report_id} className="py-1 text-xs flex items-center gap-2">
                <span className="font-mono text-[10px] text-zen-muted-text">{r.report_id}</span>
                <span className="text-zen-text-gray">
                  {new Date(r.started_at).toLocaleString()}
                </span>
                <span className="ml-auto text-[10px] text-zen-text-gray">
                  C {r.summary.critical} · W {r.summary.warn} · I {r.summary.info}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function ReviewRow({
  s,
  onApply,
  onReject,
}: {
  s: Suggestion;
  onApply: () => void;
  onReject: () => void;
}) {
  const { data: chain } = useQuery<
    ChainSummary & { steps?: Array<{ name: string; detail?: Record<string, unknown> }> }
  >({
    queryKey: ['chain-mini', s.chain_id],
    queryFn: () => apiGet(`/reasoning-chains/${encodeURIComponent(s.chain_id)}`),
    enabled: !!s.chain_id,
  });
  const adversarial = chain?.steps?.find((st) => st.name === 'adversarial')?.detail as
    | { critique?: string; severity?: string }
    | undefined;

  return (
    <li className="border border-zen-separator rounded p-2">
      <div className="flex items-baseline gap-2 flex-wrap">
        <span className="font-mono text-[10px] text-zen-muted-text">{s.kind}</span>
        {s.target && (
          <Link
            to={`/subcap?id=${encodeURIComponent(s.target)}`}
            className="font-mono text-[10px] bg-zen-light-green/60 text-zen-dark-teal px-1 rounded hover:text-zen-dark-green"
          >
            {s.target}
          </Link>
        )}
        <span className="text-sm font-medium text-zen-dark-green">{s.title}</span>
      </div>
      <p className="text-xs text-zen-text-gray mt-1">{s.rationale}</p>
      {adversarial?.critique && (
        <div className="mt-1.5 border-l-2 border-zen-orange/60 bg-zen-light-orange/20 pl-2 py-1 rounded-r">
          <div className="text-[10px] uppercase font-semibold text-zen-orange tracking-wider">
            Adversarial review
            {adversarial.severity && (
              <span className="ml-1 normal-case font-normal text-zen-text-gray">
                · severity {adversarial.severity}
              </span>
            )}
          </div>
          <div className="text-[11px] text-zen-dark-green">{adversarial.critique}</div>
        </div>
      )}
      <div className="mt-2">
        <ReasoningChainMini chain={chain ?? null} />
      </div>
      <div className="mt-2 flex items-center gap-2">
        <button
          onClick={onApply}
          className="bg-zen-teal hover:bg-zen-dark-teal text-white text-[10px] px-2 py-1 rounded inline-flex items-center gap-0.5"
        >
          <Check size={10} /> Apply
        </button>
        <button
          onClick={onReject}
          className="bg-zen-orange/80 hover:bg-zen-orange text-white text-[10px] px-2 py-1 rounded inline-flex items-center gap-0.5"
        >
          <Trash2 size={10} /> Reject
        </button>
        <span className="ml-auto text-[10px] text-zen-muted-text">
          gate {s.gate_overall} · {new Date(s.created_at).toLocaleDateString()}
        </span>
      </div>
    </li>
  );
}

function KPI({
  label,
  value,
  icon,
  tone,
}: {
  label: string;
  value: number;
  icon?: React.ReactNode;
  tone?: 'critical' | 'warn' | 'info';
}) {
  const valueClass =
    tone === 'critical'
      ? 'text-zen-orange'
      : tone === 'warn'
        ? 'text-zen-orange'
        : tone === 'info'
          ? 'text-zen-teal'
          : 'text-zen-dark-green';
  return (
    <div className="bg-white rounded-lg border border-zen-separator p-3">
      <div className="text-[10px] uppercase tracking-wider text-zen-text-gray flex items-center gap-1">
        {icon}
        {label}
      </div>
      <div className={`text-2xl font-semibold mt-1 ${valueClass}`}>{value}</div>
    </div>
  );
}
