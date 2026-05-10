import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { Tree } from '@/lib/api';

export default function CatalogueTree({ tree, search }: { tree: Tree; search: string }) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const toggle = (k: string) => setExpanded((e) => ({ ...e, [k]: !e[k] }));
  const matches = (s: string) => !search || s.toLowerCase().includes(search.toLowerCase());

  if (tree.pillars.length === 0) {
    return <div className="text-xs text-zen-dark-teal/70">No subcaps loaded yet.</div>;
  }

  return (
    <div className="text-sm">
      {tree.pillars.map((p) => (
        <div key={p.pillar_id} className="border-b border-zen-light-green/40 last:border-b-0">
          <button
            type="button"
            className="w-full flex items-center gap-1 px-2 py-1.5 hover:bg-zen-light-green/30 text-zen-dark-green font-semibold"
            onClick={() => toggle(p.pillar_id)}
          >
            {expanded[p.pillar_id] ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            <span className="text-xs bg-zen-dark-green text-white rounded px-1.5 py-px">{p.pillar_id}</span>
            <span className="ml-1">{p.name}</span>
          </button>
          {expanded[p.pillar_id] &&
            p.categories.map((c) => {
              const ck = `${p.pillar_id}.${c.category_id}`;
              return (
                <div key={ck} className="pl-5">
                  <button
                    type="button"
                    className="w-full flex items-center gap-1 px-2 py-1 hover:bg-zen-light-green/20 text-zen-dark-teal"
                    onClick={() => toggle(ck)}
                  >
                    {expanded[ck] ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                    <span className="text-[10px] uppercase tracking-wider text-zen-dark-teal/70">
                      {c.category_id}
                    </span>
                  </button>
                  {expanded[ck] &&
                    c.l1.map((l1) => {
                      const lk = `${ck}.${l1.name}`;
                      const visible = l1.subcaps.filter(
                        (s) => matches(s.sub_cap_name) || matches(s.sub_cap_id),
                      );
                      if (search && visible.length === 0) return null;
                      return (
                        <div key={lk} className="pl-5">
                          <button
                            type="button"
                            className="w-full flex items-center gap-1 px-2 py-1 hover:bg-zen-light-green/20"
                            onClick={() => toggle(lk)}
                          >
                            {expanded[lk] || search ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                            <span className="text-zen-dark-teal text-xs">{l1.name}</span>
                            <span className="text-[10px] text-zen-dark-teal/60">({visible.length}/{l1.subcaps.length})</span>
                          </button>
                          {(expanded[lk] || search) && (
                            <ul className="pl-7 pb-1.5">
                              {visible.map((s) => (
                                <li key={s.sub_cap_id}>
                                  <Link
                                    to={`/subcap?id=${encodeURIComponent(s.sub_cap_id)}`}
                                    className="block py-0.5 text-xs text-zen-dark-teal hover:text-zen-dark-green hover:bg-zen-white-green rounded px-1"
                                  >
                                    <span className="font-mono text-[10px] text-zen-dark-teal/70 mr-2">
                                      {s.sub_cap_id}
                                    </span>
                                    {s.sub_cap_name}
                                  </Link>
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                      );
                    })}
                </div>
              );
            })}
        </div>
      ))}
    </div>
  );
}
