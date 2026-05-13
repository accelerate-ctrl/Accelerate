import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowRight,
  Brain,
  CheckCircle2,
  Download,
  ExternalLink,
  FileText,
  Sparkles,
  TrendingUp,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import {
  apiGet,
  apiPost,
  type DigestPriority,
  type StrategicDigest as Digest,
} from '@/lib/api';

const STATE_BADGE: Record<string, string> = {
  EMERGING: 'bg-zen-light-orange text-zen-dark-green',
  RISING: 'bg-zen-teal text-white',
  STABLE: 'bg-zen-light-green/70 text-zen-dark-green',
  DECLINING: 'bg-zen-light-orange/70 text-zen-dark-green',
  FADING: 'bg-zen-orange/40 text-zen-dark-green',
  DEAD: 'bg-zen-dark-teal/40 text-zen-white-green',
};

const SUBVERTICAL_OPTIONS = [
  'retail-banking',
  'wealth-management',
  'asset-management',
  'insurance-life-annuity',
  'credit-unions',
  'commercial-lending',
];

const DEFAULT_PERIOD = '2026-Q2';

export default function StrategicDigest() {
  const qc = useQueryClient();
  const [subvertical, setSubvertical] = useState('retail-banking');
  const [period, setPeriod] = useState(DEFAULT_PERIOD);
  const [selected, setSelected] = useState<string | null>(null);

  const { data: digests } = useQuery<Digest[]>({
    queryKey: ['digests'],
    queryFn: () => apiGet<Digest[]>('/digest?limit=50'),
  });

  const { data: detail } = useQuery<Digest>({
    queryKey: ['digest', selected],
    enabled: !!selected,
    queryFn: () => apiGet<Digest>(`/digest/${encodeURIComponent(selected || '')}`),
  });

  const generate = useMutation({
    mutationFn: () =>
      apiPost<Digest>('/digest/generate', { subvertical, period, priority_limit: 5 }),
    onSuccess: (d) => {
      setSelected(d.digest_id);
      qc.invalidateQueries();
    },
  });

  const downloadPptx = async (digestId: string) => {
    const res = await fetch(`/api/digest/${encodeURIComponent(digestId)}/pptx`, {
      headers: { Authorization: 'Bearer dev-mishley.otiende@zennify.com' },
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${digestId}.pptx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-zen-dark-green">Quarterly Strategic Digest</h1>
        <p className="text-sm text-zen-dark-teal/80">
          Top priorities per subvertical — narrative + recommendation per priority synthesised by Claude
          Opus through the Batch-4 consultant loop. Q-over-Q deltas, evidence trail, one-click PPTX.
        </p>
      </div>

      <div className="bg-white rounded-lg border border-zen-light-green/40 p-3 grid grid-cols-1 md:grid-cols-3 gap-2 items-end">
        <label className="text-xs text-zen-dark-teal/80">
          Subvertical
          <select
            value={subvertical}
            onChange={(e) => setSubvertical(e.target.value)}
            className="block w-full mt-0.5 border border-zen-light-green rounded px-2 py-1 text-xs"
          >
            {SUBVERTICAL_OPTIONS.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </label>
        <label className="text-xs text-zen-dark-teal/80">
          Period
          <input
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            className="block w-full mt-0.5 border border-zen-light-green rounded px-2 py-1 text-xs font-mono"
            placeholder="2026-Q2"
          />
        </label>
        <button
          onClick={() => generate.mutate()}
          disabled={generate.isPending}
          className="bg-zen-teal hover:bg-zen-dark-teal text-white text-xs font-medium px-3 py-2 rounded disabled:opacity-50"
        >
          <Sparkles size={12} className={`inline mr-1 ${generate.isPending ? 'animate-pulse' : ''}`} />
          {generate.isPending ? 'Generating…' : 'Generate digest'}
        </button>
      </div>

      {generate.data && (
        <div className="bg-white border border-zen-light-green/40 rounded-lg p-3 text-xs text-zen-dark-teal flex items-start gap-2">
          <CheckCircle2 size={14} className="text-zen-teal mt-0.5" />
          <div>
            Generated <strong>{generate.data.priorities.length}</strong> priorities for{' '}
            <strong>{generate.data.subvertical}</strong> · {generate.data.period} —{' '}
            <strong>{generate.data.sources_count}</strong> sources cited; LLM cost{' '}
            <strong>${generate.data.total_cost_usd.toFixed(4)}</strong>.
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <div className="lg:col-span-1 bg-white rounded-lg border border-zen-light-green/40 p-3">
          <h2 className="text-xs uppercase font-semibold tracking-wider text-zen-dark-green mb-2">
            Recent digests ({(digests || []).length})
          </h2>
          <ul className="divide-y divide-zen-light-green/30 max-h-[640px] overflow-auto">
            {(digests || []).map((d) => (
              <li key={d.digest_id}>
                <button
                  onClick={() => setSelected(d.digest_id)}
                  className={`w-full text-left p-2 rounded hover:bg-zen-white-green/60 ${selected === d.digest_id ? 'bg-zen-white-green' : ''}`}
                >
                  <div className="flex items-center gap-2">
                    <FileText size={12} className="text-zen-teal" />
                    <span className="text-xs font-mono text-zen-dark-teal/70">{d.period}</span>
                    <span className="text-sm font-medium text-zen-dark-green">{d.subvertical}</span>
                  </div>
                  <div className="text-[10px] text-zen-dark-teal/60 mt-0.5">
                    {d.priorities.length} priorities · {d.sources_count} sources · ${d.total_cost_usd.toFixed(4)}
                  </div>
                </button>
              </li>
            ))}
            {(digests || []).length === 0 && (
              <li className="text-xs text-zen-dark-teal/60 italic py-2">
                No digests yet — pick a subvertical + period and click <strong>Generate</strong>.
              </li>
            )}
          </ul>
        </div>

        <div className="lg:col-span-2">
          {!detail && (
            <div className="bg-white rounded-lg border border-zen-light-green/40 p-6 text-center text-sm text-zen-dark-teal/70">
              Pick a digest on the left or generate a new one.
            </div>
          )}
          {detail && <DigestPanel digest={detail} onDownload={() => downloadPptx(detail.digest_id)} />}
        </div>
      </div>
    </div>
  );
}

function DigestPanel({ digest, onDownload }: { digest: Digest; onDownload: () => void }) {
  return (
    <div className="space-y-3">
      <div className="bg-white rounded-lg border border-zen-light-green/40 p-3">
        <div className="flex items-center gap-2 flex-wrap">
          <FileText size={14} className="text-zen-teal" />
          <span className="text-xs font-mono text-zen-dark-teal/70">{digest.period}</span>
          <span className="text-base font-semibold text-zen-dark-green">{digest.subvertical}</span>
          <span className="text-[10px] uppercase rounded px-1 bg-zen-light-green/40 text-zen-dark-teal">
            {digest.model}
          </span>
          <button
            onClick={onDownload}
            className="ml-auto bg-zen-teal hover:bg-zen-dark-teal text-white text-[10px] font-medium px-2 py-1 rounded inline-flex items-center gap-1"
          >
            <Download size={11} /> PPTX
          </button>
        </div>
        <p className="text-xs text-zen-dark-teal mt-2">{digest.summary}</p>
        <div className="grid grid-cols-4 gap-2 mt-2 text-[11px]">
          <KPI label="Priorities" value={digest.priorities.length} />
          <KPI label="Rising" value={digest.priorities.filter((p) => p.state === 'RISING').length} />
          <KPI label="Sources" value={digest.sources_count} />
          <KPI label="Cost (USD)" value={`$${digest.total_cost_usd.toFixed(4)}` as unknown as number} />
        </div>
      </div>

      {digest.priorities.map((p, i) => (
        <PriorityCard key={p.sub_cap_id} priority={p} rank={i + 1} previousPeriod={digest.previous_period} />
      ))}

      {digest.priorities.length === 0 && (
        <div className="bg-white rounded-lg border border-zen-light-green/40 p-6 text-center text-sm text-zen-dark-teal/70">
          No priorities matched the filter — re-run the lifecycle engine or pick another subvertical.
        </div>
      )}
    </div>
  );
}

function PriorityCard({
  priority,
  rank,
  previousPeriod,
}: {
  priority: DigestPriority;
  rank: number;
  previousPeriod: string | null;
}) {
  const state = priority.state || 'EMERGING';
  return (
    <div className="bg-white rounded-lg border border-zen-light-green/40 p-3">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-[10px] uppercase rounded px-1 bg-zen-light-green/40 text-zen-dark-teal">
          #{rank}
        </span>
        <Link to={`/subcap?id=${encodeURIComponent(priority.sub_cap_id)}`} className="font-mono text-[10px] text-zen-teal hover:text-zen-dark-teal">
          {priority.sub_cap_id}
        </Link>
        <span className={`text-[10px] uppercase rounded px-1 ${STATE_BADGE[state]}`}>{state}</span>
        <span className="text-sm font-semibold text-zen-dark-green">{priority.sub_cap_name}</span>
        <span className="text-[10px] text-zen-dark-teal/70 ml-auto">
          score {(priority.score || 0).toFixed(0)} · conf {((priority.confidence || 0) * 100).toFixed(0)}%
        </span>
      </div>

      {priority.delta && priority.delta.previous_state && (
        <div className="text-[10px] text-zen-dark-teal/60 mt-1 flex items-center gap-1">
          {previousPeriod && <span>{previousPeriod}:</span>}
          <span className="font-mono">{priority.delta.previous_state}</span>
          <ArrowRight size={9} />
          <span className="font-mono text-zen-dark-green">{state}</span>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
        <div>
          <div className="text-[10px] uppercase text-zen-dark-teal/70">Narrative</div>
          <p className="text-xs text-zen-dark-teal mt-0.5">{priority.narrative}</p>
          <div className="text-[10px] uppercase text-zen-dark-teal/70 mt-2">Recommendation</div>
          <p className="text-xs text-zen-dark-teal mt-0.5">{priority.recommendation}</p>
          {priority.chain_id && (
            <Link
              to={`/reasoning-chain?id=${encodeURIComponent(priority.chain_id)}`}
              className="text-[10px] text-zen-teal hover:text-zen-dark-teal inline-flex items-center gap-0.5 mt-1"
            >
              <Brain size={10} /> chain {priority.chain_id.slice(-6)}
            </Link>
          )}
        </div>
        <div>
          <div className="text-[10px] uppercase text-zen-dark-teal/70">Evidence</div>
          <ul className="space-y-1 mt-0.5">
            {priority.evidence_sows.slice(0, 2).map((s, i) => (
              <li key={`s${i}`} className="text-[10px] text-zen-dark-teal">
                <span className="font-mono uppercase rounded px-1 bg-zen-light-green/40 mr-1">SOW</span>
                {s.client} ({s.status}): <span className="italic">{s.excerpt?.slice(0, 120)}</span>
              </li>
            ))}
            {priority.evidence_benchmarks.slice(0, 2).map((b, i) => (
              <li key={`b${i}`} className="text-[10px] text-zen-dark-teal">
                <span className="font-mono uppercase rounded px-1 bg-zen-light-orange/60 text-zen-dark-green mr-1">BENCH</span>
                {b.metric_id} / {b.cohort_id} p50={b.p50?.toFixed(1)} ({b.verdict})
              </li>
            ))}
            {priority.evidence_news.slice(0, 1).map((n, i) => (
              <li key={`n${i}`} className="text-[10px] text-zen-dark-teal flex items-start gap-1">
                <span className="font-mono uppercase rounded px-1 bg-zen-teal/30 text-zen-dark-green mr-1">
                  <TrendingUp size={9} className="inline" /> {n.kind}
                </span>
                <span className="flex-1">[{n.source}] {n.title}</span>
                {n.url && (
                  <a href={n.url} target="_blank" rel="noreferrer" className="text-zen-teal">
                    <ExternalLink size={9} />
                  </a>
                )}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

function KPI({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="bg-zen-white-green/50 rounded p-2 text-center">
      <div className="text-xl font-semibold text-zen-dark-green">{value}</div>
      <div className="text-[10px] uppercase tracking-wider text-zen-dark-teal/70">{label}</div>
    </div>
  );
}
