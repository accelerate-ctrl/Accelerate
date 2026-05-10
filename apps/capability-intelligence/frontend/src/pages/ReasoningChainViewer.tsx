import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, AlertTriangle, XCircle, Brain, ChevronRight, Play, ExternalLink } from 'lucide-react';
import { apiGet, apiPost, type ChainStep, type GateResult, type ModelKind, type ReasoningChain } from '@/lib/api';

const VERDICT_BADGE: Record<string, string> = {
  pass: 'bg-zen-teal text-white',
  warn: 'bg-zen-light-orange text-zen-dark-green',
  fail: 'bg-zen-orange text-white',
};

function VerdictIcon({ v }: { v: string }) {
  if (v === 'pass') return <CheckCircle2 size={14} className="text-zen-teal" />;
  if (v === 'warn') return <AlertTriangle size={14} className="text-zen-orange" />;
  return <XCircle size={14} className="text-zen-orange" />;
}

export default function ReasoningChainViewer() {
  const qc = useQueryClient();
  const [open, setOpen] = useState<string | null>(null);
  const [query, setQuery] = useState('audit subcap evidence + propose suggestions');
  const [subcap, setSubcap] = useState('P1C1.1.1');
  const [model, setModel] = useState<ModelKind>('gemini-flash');

  const { data: chains } = useQuery<Array<Pick<ReasoningChain, 'chain_id' | 'sub_cap_id' | 'started_at' | 'completed_at' | 'overall' | 'total_cost_usd'> & { gates: ReasoningChain['gates']; suggestions: ReasoningChain['suggestions']; output: ReasoningChain['output'] }>>({
    queryKey: ['chains'],
    queryFn: () => apiGet('/reasoning-chains?limit=50'),
  });

  const { data: detail } = useQuery<ReasoningChain>({
    queryKey: ['chain', open],
    enabled: !!open,
    queryFn: () => apiGet<ReasoningChain>(`/reasoning-chains/${encodeURIComponent(open || '')}`),
  });

  const trigger = useMutation({
    mutationFn: () => apiPost<{ chain_id: string }>('/reasoning-chains/run', { query, sub_cap_id: subcap, model }),
    onSuccess: (d) => {
      setOpen(d.chain_id);
      qc.invalidateQueries();
    },
  });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-zen-dark-green">Reasoning Chain Viewer</h1>
        <p className="text-sm text-zen-dark-teal/80">
          7-step consultant loop traces: <strong>clarify → retrieve internal → retrieve external → synthesize → adversarial → propose → gate → finalize</strong>.
          Every claim is grounded in a source row, every step records cost.
        </p>
      </div>

      <div className="bg-white rounded-lg border border-zen-light-green/40 p-3 grid grid-cols-1 md:grid-cols-4 gap-2 items-end">
        <label className="text-xs text-zen-dark-teal/80 col-span-2">
          Query
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="block w-full mt-0.5 border border-zen-light-green rounded px-2 py-1 text-xs"
          />
        </label>
        <label className="text-xs text-zen-dark-teal/80">
          Subcap
          <input
            value={subcap}
            onChange={(e) => setSubcap(e.target.value)}
            className="block w-full mt-0.5 border border-zen-light-green rounded px-2 py-1 text-xs font-mono"
          />
        </label>
        <label className="text-xs text-zen-dark-teal/80">
          Model
          <select
            value={model}
            onChange={(e) => setModel(e.target.value as ModelKind)}
            className="block w-full mt-0.5 border border-zen-light-green rounded px-2 py-1 text-xs"
          >
            <option value="gemini-flash">gemini-flash (cheap claim extract)</option>
            <option value="gemini-pro">gemini-pro (synthesis)</option>
            <option value="sonnet">sonnet (high-quality reasoning)</option>
            <option value="opus">opus (digest only)</option>
          </select>
        </label>
        <div className="md:col-span-4 flex items-center gap-2">
          <button
            onClick={() => trigger.mutate()}
            disabled={trigger.isPending}
            className="bg-zen-teal hover:bg-zen-dark-teal text-white text-xs font-medium px-3 py-1.5 rounded transition-colors disabled:opacity-50"
          >
            <Play size={12} className="inline mr-1" /> {trigger.isPending ? 'Running…' : 'Run loop'}
          </button>
          {trigger.error && <span className="text-xs text-zen-orange">{(trigger.error as Error).message}</span>}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <div className="lg:col-span-1 bg-white rounded-lg border border-zen-light-green/40 p-3">
          <h2 className="text-xs uppercase font-semibold tracking-wider text-zen-dark-green mb-2">
            Recent runs ({chains?.length ?? 0})
          </h2>
          <ul className="divide-y divide-zen-light-green/30 max-h-[640px] overflow-auto">
            {chains?.map((c) => (
              <li key={c.chain_id}>
                <button
                  className={`w-full text-left p-2 hover:bg-zen-white-green/60 rounded ${open === c.chain_id ? 'bg-zen-white-green/80' : ''}`}
                  onClick={() => setOpen(c.chain_id)}
                >
                  <div className="flex items-center gap-2">
                    <VerdictIcon v={c.overall} />
                    <span className="font-mono text-[10px] text-zen-dark-teal/70">{c.chain_id.slice(-6)}</span>
                    <span className="text-xs font-mono text-zen-dark-green">{c.sub_cap_id}</span>
                    <ChevronRight size={12} className="ml-auto text-zen-dark-teal/40" />
                  </div>
                  <div className="text-[10px] text-zen-dark-teal/60 mt-0.5">
                    {new Date(c.started_at).toLocaleString()} · ${c.total_cost_usd.toFixed(4)}
                  </div>
                  <div className="text-[10px] text-zen-dark-teal mt-0.5">
                    gates: {c.gates?.score?.toFixed(2)} · {c.suggestions?.length || 0} suggestions
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="lg:col-span-2 space-y-3">
          {!detail && <div className="bg-white rounded-lg border border-zen-light-green/40 p-6 text-center text-sm text-zen-dark-teal/70">Pick a run on the left, or trigger a new one.</div>}
          {detail && <ChainDetail chain={detail} />}
        </div>
      </div>
    </div>
  );
}

function ChainDetail({ chain }: { chain: ReasoningChain }) {
  return (
    <>
      <div className="bg-white rounded-lg border border-zen-light-green/40 p-3 text-xs space-y-1 text-zen-dark-teal">
        <div className="flex items-center gap-2">
          <Brain size={14} className="text-zen-teal" />
          <span className="font-mono text-zen-dark-green">{chain.chain_id}</span>
          <span className={`uppercase rounded px-1.5 py-0.5 text-[10px] ${VERDICT_BADGE[chain.overall]}`}>{chain.overall}</span>
          <span className="text-zen-dark-teal/60">·</span>
          <span>cost ${chain.total_cost_usd.toFixed(4)}</span>
          <span className="text-zen-dark-teal/60">·</span>
          <span>gate score {chain.gates.score.toFixed(2)}</span>
        </div>
      </div>

      <Section title="Steps">
        <ol className="space-y-1">
          {chain.steps.map((s, i) => (
            <StepRow key={i} step={s} />
          ))}
        </ol>
      </Section>

      <Section title={`Claims (${chain.output.claims?.length || 0})`}>
        <ul className="space-y-1 text-xs">
          {(chain.output.claims || []).map((c, i) => (
            <li key={i} className="text-zen-dark-teal">
              <span className="font-mono text-[10px] text-zen-dark-teal/60 mr-1">[{i}]</span>
              {c.text}
              {c.subcap_id && (
                <span className="font-mono text-[10px] bg-zen-light-green/50 text-zen-dark-teal px-1 rounded ml-2">
                  {c.subcap_id}
                </span>
              )}
              <span className="text-[10px] text-zen-dark-teal/60 ml-2">→ {(c.sources || []).join(', ') || 'no source'}</span>
            </li>
          ))}
        </ul>
      </Section>

      <Section title={`Sources (${chain.sources.length})`}>
        <ul className="space-y-1 text-xs">
          {chain.sources.map((s) => (
            <li key={s.id} className="text-zen-dark-teal">
              <span className="font-mono text-[10px] text-zen-dark-teal/60 mr-1">{s.id}</span>
              <span className="text-[10px] uppercase rounded px-1 bg-zen-light-orange/60 text-zen-dark-green mr-2">{s.kind}</span>
              {s.title}
              {s.url && (
                <a href={s.url} target="_blank" rel="noreferrer" className="ml-2 text-zen-teal hover:text-zen-dark-teal inline-flex items-center gap-0.5">
                  <ExternalLink size={9} />
                </a>
              )}
            </li>
          ))}
        </ul>
      </Section>

      <Section title={`Gates (${chain.gates.results.length})`}>
        <ul className="grid grid-cols-1 md:grid-cols-2 gap-1 text-xs">
          {chain.gates.results.map((g) => (
            <GateRow key={g.name} gate={g} />
          ))}
        </ul>
      </Section>

      {chain.suggestions.length > 0 && (
        <Section title={`Suggestions (${chain.suggestions.length})`}>
          <ul className="space-y-1 text-xs">
            {chain.suggestions.map((s, i) => (
              <li key={i} className="text-zen-dark-teal">
                <span className="font-mono text-[10px] text-zen-dark-teal/60 mr-1">{s.kind}</span>
                <strong>{s.title}</strong>
                {s.target && <span className="font-mono text-[10px] bg-zen-light-green/50 text-zen-dark-teal px-1 rounded ml-2">{s.target}</span>}
                <div className="text-[10px] text-zen-dark-teal/70 mt-0.5">{s.rationale}</div>
              </li>
            ))}
          </ul>
        </Section>
      )}
    </>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-lg border border-zen-light-green/40 p-3">
      <h3 className="text-xs uppercase font-semibold tracking-wider text-zen-dark-green mb-2">{title}</h3>
      {children}
    </div>
  );
}

function StepRow({ step }: { step: ChainStep }) {
  return (
    <li className="grid grid-cols-[140px_1fr_auto] gap-2 text-xs items-baseline">
      <span className="font-mono text-zen-dark-green">{step.name}</span>
      <span className="text-zen-dark-teal">{step.output_summary || step.input_summary || '—'}</span>
      <span className="text-[10px] text-zen-dark-teal/60">
        {step.model && <>{step.model} · </>}
        {step.cached && <>cached · </>}
        {step.tokens_in != null && <>{step.tokens_in}/{step.tokens_out}t · </>}
        ${(step.cost_usd ?? 0).toFixed(4)}
      </span>
    </li>
  );
}

function GateRow({ gate }: { gate: GateResult }) {
  return (
    <li className="flex items-start gap-1">
      <VerdictIcon v={gate.verdict} />
      <div>
        <span className="font-mono text-[10px] text-zen-dark-green">{gate.name}</span>
        <span className="text-[10px] text-zen-dark-teal/60 ml-1">({gate.score.toFixed(2)})</span>
        <div className="text-[10px] text-zen-dark-teal/70">{gate.reasoning}</div>
      </div>
    </li>
  );
}
