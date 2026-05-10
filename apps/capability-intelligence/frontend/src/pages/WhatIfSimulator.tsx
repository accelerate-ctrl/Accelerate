import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { ArrowRight, FlaskConical, Plus, Trash2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import { apiPost, type WhatIfSimulation } from '@/lib/api';

type Action = {
  kind:
    | 'add_sow_mention'
    | 'set_lifecycle_state'
    | 'promote_vendor'
    | 'add_news_mention';
  target: Record<string, string | number>;
};

const STATE_BADGE: Record<string, string> = {
  EMERGING: 'bg-zen-light-orange text-zen-dark-green',
  RISING: 'bg-zen-teal text-white',
  STABLE: 'bg-zen-light-green/70 text-zen-dark-green',
  DECLINING: 'bg-zen-light-orange/70 text-zen-dark-green',
  FADING: 'bg-zen-orange/40 text-zen-dark-green',
  DEAD: 'bg-zen-dark-teal/40 text-zen-white-green',
};

const KIND_HELP: Record<string, string> = {
  add_sow_mention: 'Add a synthetic active-status SOW mention; recomputes lifecycle score.',
  set_lifecycle_state: 'Force a state override (no rule recompute).',
  promote_vendor: 'Override the (vendor, cohort) adoption %.',
  add_news_mention: 'Bump news_last_90d for the subcap.',
};

const VALID_STATES = ['EMERGING', 'RISING', 'STABLE', 'DECLINING', 'FADING', 'DEAD'];

export default function WhatIfSimulator() {
  const [actions, setActions] = useState<Action[]>([
    { kind: 'add_sow_mention', target: { sub_cap_id: 'P1C1.1.1' } },
  ]);
  const simulate = useMutation({
    mutationFn: () =>
      apiPost<WhatIfSimulation>('/what-if/simulate', { actions }),
  });

  const updateAction = (i: number, patch: Partial<Action>) => {
    setActions((prev) =>
      prev.map((a, idx) =>
        idx === i ? { ...a, ...patch, target: { ...a.target, ...(patch.target || {}) } } : a,
      ),
    );
  };

  const setKind = (i: number, kind: Action['kind']) => {
    const defaults: Record<Action['kind'], Action['target']> = {
      add_sow_mention: { sub_cap_id: 'P1C1.1.1' },
      set_lifecycle_state: { sub_cap_id: 'P1C1.1.1', state: 'STABLE' },
      promote_vendor: {
        vendor_id: 'salesforce_financial_services_cloud',
        cohort_id: 'us_banks_gsib',
        adoption_pct: 80,
      },
      add_news_mention: { sub_cap_id: 'P1C1.1.1' },
    };
    setActions((prev) =>
      prev.map((a, idx) => (idx === i ? { kind, target: defaults[kind] } : a)),
    );
  };

  const removeAction = (i: number) =>
    setActions((prev) => prev.filter((_, idx) => idx !== i));

  const addAction = () =>
    setActions((prev) => [
      ...prev,
      { kind: 'add_sow_mention', target: { sub_cap_id: 'P1C1.1.2' } },
    ]);

  const sim = simulate.data;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold text-zen-dark-green">What-If Simulator</h1>
        <p className="text-sm text-zen-dark-teal/80">
          Apply hypothetical actions to the Batch-6 synthesis layer and preview the ripple
          on lifecycle states + vendor adoption. <strong>Read-only</strong>: nothing here
          mutates the live repository.
        </p>
      </div>

      <div className="bg-white rounded-lg border border-zen-light-green/40 p-3">
        <h2 className="text-xs uppercase font-semibold tracking-wider text-zen-dark-green mb-2">
          Actions
        </h2>
        <ul className="space-y-2">
          {actions.map((a, i) => (
            <li key={i} className="border border-zen-light-green/40 rounded p-2 text-xs">
              <div className="flex items-center gap-2 flex-wrap">
                <select
                  value={a.kind}
                  onChange={(e) => setKind(i, e.target.value as Action['kind'])}
                  className="border border-zen-light-green rounded px-2 py-1 text-xs"
                >
                  <option value="add_sow_mention">add SOW mention</option>
                  <option value="set_lifecycle_state">set lifecycle state</option>
                  <option value="promote_vendor">promote vendor</option>
                  <option value="add_news_mention">add news mention</option>
                </select>
                <span className="text-[10px] text-zen-dark-teal/70">{KIND_HELP[a.kind]}</span>
                <button
                  type="button"
                  onClick={() => removeAction(i)}
                  className="ml-auto text-zen-orange hover:text-zen-dark-teal"
                >
                  <Trash2 size={12} />
                </button>
              </div>
              <div className="mt-1 grid grid-cols-2 md:grid-cols-3 gap-1 text-[10px]">
                {Object.entries(a.target).map(([key, value]) => (
                  <label key={key} className="flex flex-col text-zen-dark-teal/70">
                    {key}
                    {key === 'state' ? (
                      <select
                        value={String(value)}
                        onChange={(e) =>
                          updateAction(i, { target: { [key]: e.target.value } })
                        }
                        className="border border-zen-light-green rounded px-1 py-0.5 text-xs mt-0.5"
                      >
                        {VALID_STATES.map((s) => (
                          <option key={s} value={s}>{s}</option>
                        ))}
                      </select>
                    ) : (
                      <input
                        type={typeof value === 'number' ? 'number' : 'text'}
                        value={String(value)}
                        onChange={(e) =>
                          updateAction(i, {
                            target: {
                              [key]:
                                typeof value === 'number'
                                  ? Number(e.target.value)
                                  : e.target.value,
                            },
                          })
                        }
                        className="border border-zen-light-green rounded px-1 py-0.5 text-xs mt-0.5 font-mono"
                      />
                    )}
                  </label>
                ))}
              </div>
            </li>
          ))}
        </ul>
        <div className="mt-2 flex items-center gap-2">
          <button
            type="button"
            onClick={addAction}
            className="bg-zen-light-green/60 hover:bg-zen-light-green text-zen-dark-green text-[10px] font-medium px-2 py-1 rounded inline-flex items-center gap-1"
          >
            <Plus size={11} /> add action
          </button>
          <button
            type="button"
            onClick={() => simulate.mutate()}
            disabled={simulate.isPending || actions.length === 0}
            className="bg-zen-teal hover:bg-zen-dark-teal text-white text-xs font-medium px-3 py-1.5 rounded disabled:opacity-50 inline-flex items-center gap-1"
          >
            <FlaskConical size={11} className={simulate.isPending ? 'animate-pulse' : ''} />
            {simulate.isPending ? 'Simulating…' : 'Run simulation'}
          </button>
        </div>
      </div>

      {sim && (
        <>
          <div className="bg-white rounded-lg border border-zen-light-green/40 p-3 text-xs text-zen-dark-teal">
            {sim.summary}
          </div>

          {sim.state_changes.length > 0 && (
            <div className="bg-white rounded-lg border border-zen-light-green/40 p-3">
              <h3 className="text-xs uppercase font-semibold tracking-wider text-zen-dark-green mb-2">
                Lifecycle deltas ({sim.state_changes.length})
              </h3>
              <ul className="divide-y divide-zen-light-green/30">
                {sim.state_changes.map((c, i) => (
                  <li key={i} className="py-1 text-xs flex items-center gap-2 flex-wrap">
                    <Link
                      to={`/subcap?id=${encodeURIComponent(c.sub_cap_id)}`}
                      className="font-mono text-[10px] text-zen-teal hover:text-zen-dark-teal"
                    >
                      {c.sub_cap_id}
                    </Link>
                    <span className="text-zen-dark-green">{c.sub_cap_name}</span>
                    <span className="ml-auto inline-flex items-center gap-1">
                      <span className={`text-[10px] uppercase rounded px-1 ${STATE_BADGE[c.before.state || ''] || ''}`}>
                        {c.before.state || 'n/a'}
                      </span>
                      <ArrowRight size={10} className="text-zen-dark-teal/60" />
                      <span className={`text-[10px] uppercase rounded px-1 ${STATE_BADGE[c.after.state] || ''}`}>
                        {c.after.state}
                      </span>
                      <span className="text-[10px] text-zen-dark-teal/60 ml-2">
                        {(c.before.score || 0).toFixed(0)} → {c.after.score.toFixed(0)}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {sim.adoption_changes.length > 0 && (
            <div className="bg-white rounded-lg border border-zen-light-green/40 p-3">
              <h3 className="text-xs uppercase font-semibold tracking-wider text-zen-dark-green mb-2">
                Adoption deltas ({sim.adoption_changes.length})
              </h3>
              <ul className="divide-y divide-zen-light-green/30">
                {sim.adoption_changes.map((c, i) => (
                  <li key={i} className="py-1 text-xs flex items-center gap-2">
                    <span className="font-mono text-[10px] text-zen-dark-teal">{c.vendor_id}</span>
                    <span className="font-mono text-[10px] text-zen-dark-teal/70">{c.cohort_id}</span>
                    <span className="ml-auto">
                      {c.before_pct.toFixed(0)}% <ArrowRight size={10} className="inline text-zen-dark-teal/60" /> <strong>{c.after_pct.toFixed(0)}%</strong>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {sim.new_transitions.length > 0 && (
            <div className="bg-white rounded-lg border border-zen-light-green/40 p-3">
              <h3 className="text-xs uppercase font-semibold tracking-wider text-zen-dark-green mb-2">
                Hypothetical transitions ({sim.new_transitions.length})
              </h3>
              <ul className="space-y-1 text-xs">
                {sim.new_transitions.map((t, i) => (
                  <li key={i} className="flex items-center gap-2">
                    <span className="font-mono text-[10px] text-zen-teal">{t.sub_cap_id}</span>
                    <span className={`text-[10px] uppercase rounded px-1 ${STATE_BADGE[t.from_state] || ''}`}>
                      {t.from_state}
                    </span>
                    <ArrowRight size={10} className="text-zen-dark-teal/60" />
                    <span className={`text-[10px] uppercase rounded px-1 ${STATE_BADGE[t.to_state] || ''}`}>
                      {t.to_state}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}
