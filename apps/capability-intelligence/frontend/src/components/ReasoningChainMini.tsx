// ReasoningChainMini — a compact, reusable strip that visualises a
// consultant-loop chain inline. Used on Suggestion cards, Subcap Deep
// Dive, and Strategic Digest priority cards so users see the AI's
// reasoning without leaving the page they're on.
import { Link } from 'react-router-dom';
import { Brain, ChevronRight } from 'lucide-react';

export type ChainStep = {
  name: string;
  model?: string | null;
  cost_usd?: number;
  cached?: boolean;
  detail?: Record<string, unknown>;
};

export type ChainSummary = {
  chain_id: string;
  overall?: string;             // pass | warn | fail
  total_cost_usd?: number;
  steps?: ChainStep[];
  started_at?: string;
};

const STEP_ICON: Record<string, string> = {
  clarify: '✦',
  retrieve_internal: '📂',
  retrieve_external: '🌐',
  synthesize: '✶',
  adversarial: '⚔',
  propose_suggestions: '◇',
  gate: '⊕',
  finalize: '✓',
};

const VERDICT_STYLE: Record<string, string> = {
  pass: 'bg-zen-light-green/70 text-zen-dark-green',
  warn: 'bg-zen-light-orange/70 text-zen-orange',
  fail: 'bg-zen-light-orange/90 text-zen-orange',
};

export default function ReasoningChainMini({ chain }: { chain: ChainSummary | null | undefined }) {
  if (!chain) {
    return (
      <div className="text-[10px] text-zen-muted-text italic">
        No reasoning chain attached yet — run the loop to generate one.
      </div>
    );
  }
  const steps = chain.steps || [];
  const verdict = (chain.overall || 'pass').toLowerCase();
  const verdictClass = VERDICT_STYLE[verdict] || VERDICT_STYLE.pass;

  return (
    <Link
      to={`/reasoning?id=${encodeURIComponent(chain.chain_id)}`}
      className="block bg-zen-ice/60 border border-zen-separator rounded p-2 hover:bg-zen-ice transition-colors"
      aria-label={`reasoning chain ${chain.chain_id}`}
    >
      <div className="flex items-center gap-2 mb-1">
        <Brain size={12} className="text-zen-teal" aria-hidden />
        <span className="font-mono text-[10px] text-zen-muted-text">
          {chain.chain_id.slice(-8)}
        </span>
        <span
          className={`text-[9px] uppercase tracking-wider font-semibold rounded px-1.5 py-0.5 ${verdictClass}`}
        >
          {verdict}
        </span>
        {typeof chain.total_cost_usd === 'number' && chain.total_cost_usd > 0 && (
          <span className="ml-auto text-[10px] text-zen-muted-text">
            ${chain.total_cost_usd.toFixed(4)}
          </span>
        )}
      </div>
      {steps.length > 0 && (
        <div className="flex items-center gap-0.5 flex-wrap text-[10px]">
          {steps.map((s, i) => (
            <span key={i} className="inline-flex items-center gap-0.5">
              <span
                className="bg-white border border-zen-separator rounded px-1.5 py-0.5 inline-flex items-center gap-1"
                title={`${s.name}${s.model ? ` · ${s.model}` : ''}${s.cached ? ' · cached' : ''}`}
              >
                <span className="text-zen-teal">{STEP_ICON[s.name] || '•'}</span>
                <span className="text-zen-text-gray uppercase tracking-wider">
                  {s.name.replace(/_/g, ' ')}
                </span>
              </span>
              {i < steps.length - 1 && (
                <ChevronRight size={10} className="text-zen-muted-text shrink-0" aria-hidden />
              )}
            </span>
          ))}
        </div>
      )}
    </Link>
  );
}
