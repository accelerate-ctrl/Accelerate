import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  CheckCircle2,
  Info,
  Play,
  ShieldAlert,
  XCircle,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { apiGet, apiPost, type AuditFinding, type AuditReport } from '@/lib/api';

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

  const latest = reports && reports[0];

  const run = useMutation({
    mutationFn: () => apiPost<AuditReport>('/audit/run'),
    onSettled: () => qc.invalidateQueries(),
  });

  const visibleFindings: AuditFinding[] = (latest?.findings || []).filter(
    (f) => filter === 'all' || f.severity === filter,
  );

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-zen-dark-green">QA & Audit Dashboard</h1>
          <p className="text-sm text-zen-dark-teal/80">
            Weekly deep-audit sweeps every consultant-loop chain, every pending suggestion,
            every flag, and every dead-state subcap. Severity-rolled findings with drill-back.
          </p>
        </div>
        <button
          onClick={() => run.mutate()}
          disabled={run.isPending}
          className="bg-zen-teal hover:bg-zen-dark-teal text-white text-xs font-medium px-3 py-1.5 rounded transition-colors disabled:opacity-50"
        >
          <Play size={12} className={`inline mr-1 ${run.isPending ? 'animate-pulse' : ''}`} /> Run audit
        </button>
      </div>

      {latest && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <KPI label="Findings" value={latest.findings.length} icon={<ShieldAlert size={12} />} />
          <KPI label="Critical" value={latest.summary.critical} tone="critical" />
          <KPI label="Warn" value={latest.summary.warn} tone="warn" />
          <KPI label="Info" value={latest.summary.info} tone="info" />
        </div>
      )}

      {!latest && (
        <div className="bg-white rounded-lg border border-zen-light-green/40 p-6 text-center text-sm text-zen-dark-teal/70">
          No audits yet — click <strong>Run audit</strong>.
        </div>
      )}

      {latest && (
        <div className="bg-white rounded-lg border border-zen-light-green/40 p-3">
          <div className="flex items-center gap-2 text-xs text-zen-dark-teal/70 mb-2">
            <CheckCircle2 size={14} className="text-zen-teal" />
            <span>Latest report <strong className="font-mono text-zen-dark-green">{latest.report_id}</strong></span>
            <span>·</span>
            <span>{new Date(latest.started_at).toLocaleString()}</span>
            <div className="ml-auto flex gap-1">
              {(['all', 'critical', 'warn', 'info'] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={`text-[10px] uppercase rounded px-1.5 py-0.5 ${filter === f ? 'bg-zen-dark-green text-white' : 'bg-zen-light-green/40 text-zen-dark-teal/80'}`}
                >
                  {f}
                </button>
              ))}
            </div>
          </div>
          <ul className="divide-y divide-zen-light-green/30 max-h-[640px] overflow-auto">
            {visibleFindings.length === 0 && (
              <li className="text-xs text-zen-dark-teal/60 italic py-2">
                No findings for this severity filter.
              </li>
            )}
            {visibleFindings.map((f, i) => (
              <li key={i} className="py-2 text-xs">
                <div className="flex items-center gap-2 flex-wrap">
                  <SevIcon s={f.severity} />
                  <span className={`uppercase rounded px-1 ${SEVERITY_BADGE[f.severity]}`}>{f.severity}</span>
                  <span className="font-mono text-[10px] text-zen-dark-teal/70">{f.kind}</span>
                  <span className="text-zen-dark-green font-medium">{f.title}</span>
                  {f.ref_collection === 'reasoning_chains' && f.ref_id && (
                    <Link
                      to={`/reasoning-chain?id=${encodeURIComponent(f.ref_id)}`}
                      className="ml-auto text-[10px] text-zen-teal hover:text-zen-dark-teal underline"
                    >
                      view chain
                    </Link>
                  )}
                  {f.ref_collection === 'suggestions' && f.ref_id && (
                    <Link
                      to={`/ai-suggestions`}
                      className="ml-auto text-[10px] text-zen-teal hover:text-zen-dark-teal underline"
                    >
                      view suggestion
                    </Link>
                  )}
                  {f.ref_collection === 'lifecycle_scores' && f.ref_id && (
                    <Link
                      to={`/subcap?id=${encodeURIComponent(f.ref_id)}`}
                      className="ml-auto text-[10px] text-zen-teal hover:text-zen-dark-teal underline"
                    >
                      view subcap
                    </Link>
                  )}
                </div>
                <div className="text-[10px] text-zen-dark-teal/70 mt-0.5">{f.detail}</div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {(reports || []).length > 1 && (
        <div className="bg-white rounded-lg border border-zen-light-green/40 p-3">
          <h2 className="text-xs uppercase font-semibold tracking-wider text-zen-dark-green mb-2">
            History
          </h2>
          <ul className="divide-y divide-zen-light-green/30">
            {(reports || []).slice(1).map((r) => (
              <li key={r.report_id} className="py-1 text-xs flex items-center gap-2">
                <span className="font-mono text-[10px] text-zen-dark-teal/70">{r.report_id}</span>
                <span className="text-zen-dark-teal/70">{new Date(r.started_at).toLocaleString()}</span>
                <span className="ml-auto text-[10px] text-zen-dark-teal">
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
    <div className="bg-white rounded-lg border border-zen-light-green/40 p-3">
      <div className="text-[10px] uppercase tracking-wider text-zen-dark-teal/70 flex items-center gap-1">
        {icon}
        {label}
      </div>
      <div className={`text-2xl font-semibold mt-1 ${valueClass}`}>{value}</div>
    </div>
  );
}
