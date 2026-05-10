import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, AlertTriangle, XCircle, Shield } from 'lucide-react';
import { Link } from 'react-router-dom';
import { apiGet, type GateRunRow, type GateSummary } from '@/lib/api';

const VERDICT_CLASS: Record<string, string> = {
  pass: 'bg-zen-teal/30 text-zen-dark-green',
  warn: 'bg-zen-light-orange text-zen-dark-green',
  fail: 'bg-zen-orange text-white',
};

function VerdictIcon({ v }: { v: string }) {
  if (v === 'pass') return <CheckCircle2 size={12} className="text-zen-teal" />;
  if (v === 'warn') return <AlertTriangle size={12} className="text-zen-orange" />;
  return <XCircle size={12} className="text-zen-orange" />;
}

export default function ValidationGatesLog() {
  const { data: summary } = useQuery<GateSummary>({
    queryKey: ['gate-summary'],
    queryFn: () => apiGet<GateSummary>('/validation-gates/summary'),
  });
  const { data: runs } = useQuery<GateRunRow[]>({
    queryKey: ['gate-runs'],
    queryFn: () => apiGet<GateRunRow[]>('/validation-gates/runs?limit=50'),
  });

  const gates = summary ? Object.keys(summary.by_gate).sort() : [];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-zen-dark-green">Validation Gates</h1>
        <p className="text-sm text-zen-dark-teal/80">
          Aggregate verdicts from the 8-gate engine across every consultant-loop run. Daily + weekly cost
          guardrails roll up here too.
        </p>
      </div>

      {summary && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <KPI title="Total runs" value={String(summary.total_runs)} icon={<Shield size={14} />} />
          <KPI title="Spend (today)" value={`$${summary.cost_summary.today_usd.toFixed(4)}`} sub={`${summary.cost_summary.today_calls} calls`} />
          <KPI title="Spend (7d)" value={`$${summary.cost_summary.week_usd.toFixed(4)}`} sub={`${summary.cost_summary.week_calls} calls`} />
        </div>
      )}

      <div className="bg-white rounded-lg border border-zen-light-green/40 p-3">
        <h2 className="text-xs uppercase font-semibold tracking-wider text-zen-dark-green mb-2">
          Per-gate distribution
        </h2>
        <div className="overflow-x-auto">
          <table className="text-xs w-full">
            <thead className="text-zen-dark-teal/60">
              <tr>
                <th className="text-left">Gate</th>
                <th className="text-right">Pass</th>
                <th className="text-right">Warn</th>
                <th className="text-right">Fail</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zen-light-green/30">
              {gates.map((g) => {
                const counts = summary!.by_gate[g] || {};
                return (
                  <tr key={g}>
                    <td className="font-mono text-zen-dark-green py-1">{g}</td>
                    <td className="text-right text-zen-teal">{counts.pass || 0}</td>
                    <td className="text-right text-zen-orange">{counts.warn || 0}</td>
                    <td className="text-right text-zen-orange font-bold">{counts.fail || 0}</td>
                  </tr>
                );
              })}
              {!gates.length && <tr><td colSpan={4} className="text-zen-dark-teal/60 italic py-1">No runs yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      <div className="bg-white rounded-lg border border-zen-light-green/40 p-3">
        <h2 className="text-xs uppercase font-semibold tracking-wider text-zen-dark-green mb-2">
          Recent runs
        </h2>
        <ul className="divide-y divide-zen-light-green/30">
          {runs?.map((r) => (
            <li key={r.chain_id} className="py-2 text-xs">
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`uppercase rounded px-1.5 py-0.5 text-[10px] ${VERDICT_CLASS[r.overall]}`}>{r.overall}</span>
                <Link
                  to={`/reasoning-chain?id=${encodeURIComponent(r.chain_id)}`}
                  className="font-mono text-[10px] text-zen-teal hover:text-zen-dark-teal"
                >
                  {r.chain_id.slice(-8)}
                </Link>
                {r.sub_cap_id && <span className="font-mono text-[10px] text-zen-dark-green">{r.sub_cap_id}</span>}
                <span className="text-zen-dark-teal/60">score {r.score?.toFixed(2)}</span>
                <span className="text-zen-dark-teal/60 ml-auto">{new Date(r.completed_at).toLocaleString()}</span>
              </div>
              <div className="flex flex-wrap gap-1 mt-1">
                {r.results.map((g) => (
                  <span
                    key={g.name}
                    className={`text-[10px] rounded px-1 inline-flex items-center gap-0.5 ${VERDICT_CLASS[g.verdict]}`}
                    title={g.reasoning}
                  >
                    <VerdictIcon v={g.verdict} /> {g.name}
                  </span>
                ))}
              </div>
            </li>
          ))}
          {!runs?.length && <li className="text-zen-dark-teal/60 italic py-1 text-xs">No runs yet.</li>}
        </ul>
      </div>
    </div>
  );
}

function KPI({ title, value, sub, icon }: { title: string; value: string; sub?: string; icon?: React.ReactNode }) {
  return (
    <div className="bg-white rounded-lg border border-zen-light-green/40 p-3">
      <div className="text-[10px] uppercase tracking-wider text-zen-dark-teal/70 flex items-center gap-1">
        {icon}
        {title}
      </div>
      <div className="text-2xl font-semibold text-zen-dark-green mt-1">{value}</div>
      {sub && <div className="text-[10px] text-zen-dark-teal/60">{sub}</div>}
    </div>
  );
}
