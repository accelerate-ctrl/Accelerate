import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Loader2, Search, X } from 'lucide-react';
import { apiGet } from '@/lib/api';

/**
 * IMP-1 — global Cmd/Ctrl+K command palette.
 *
 * Searches across:
 *  - subcap names + ids
 *  - L3 platform names + ids
 *  - vendor names
 *  - story keys
 *  - recent reasoning-chain ids
 *
 * Results are scored locally against a refreshed-on-open index so
 * keystrokes complete in <100ms even when the catalogue has ~15k rows.
 */

type CommandItem = {
  id: string;
  label: string;
  subtitle?: string;
  kind: 'subcap' | 'l3' | 'vendor' | 'story' | 'chain' | 'page';
  to: string;
};

const STATIC_PAGES: CommandItem[] = [
  { id: 'p:explorer', label: 'Capability Explorer', kind: 'page', to: '/explorer' },
  { id: 'p:graph', label: 'Knowledge Graph', kind: 'page', to: '/graph' },
  { id: 'p:news', label: 'News Watch', kind: 'page', to: '/news' },
  { id: 'p:trends', label: 'Trends Monitor', kind: 'page', to: '/trends' },
  { id: 'p:suggestions', label: 'AI Suggestions', kind: 'page', to: '/suggestions' },
  { id: 'p:digest', label: 'Strategic Digest', kind: 'page', to: '/digest' },
  { id: 'p:lifecycle', label: 'Lifecycle Manager', kind: 'page', to: '/lifecycle' },
  { id: 'p:benchmarks', label: 'Benchmarks Studio', kind: 'page', to: '/benchmarks' },
  { id: 'p:flags', label: 'Change Flags Inbox', kind: 'page', to: '/flags' },
  { id: 'p:versions', label: 'Version Timeline', kind: 'page', to: '/versions' },
  { id: 'p:vendors', label: 'Vendor Intelligence', kind: 'page', to: '/vendors' },
  { id: 'p:stories', label: 'Story Library', kind: 'page', to: '/stories' },
  { id: 'p:chat', label: 'AI Chat', kind: 'page', to: '/chat' },
  { id: 'p:reasoning', label: 'Reasoning Chain Viewer', kind: 'page', to: '/reasoning' },
  { id: 'p:settings', label: 'Settings', kind: 'page', to: '/settings' },
];

type SubcapRow = { sub_cap_id: string; sub_cap_name: string; pillar_id?: string };
type L3Row = { l3_id: string; name: string; vendor?: string };
type ChainRow = { chain_id: string; operation?: string; sub_cap_id?: string };

const MAX_RESULTS = 12;

function scoreMatch(query: string, candidate: string): number {
  if (!query) return 0;
  const q = query.toLowerCase();
  const c = candidate.toLowerCase();
  if (c === q) return 1000;
  if (c.startsWith(q)) return 500;
  const idx = c.indexOf(q);
  if (idx >= 0) return 200 - idx; // earlier-position matches outrank later ones
  // Fallback: count distinct token hits in the candidate.
  const tokens = q.split(/\s+/).filter(Boolean);
  let hits = 0;
  for (const t of tokens) if (c.includes(t)) hits += 1;
  return hits * 50;
}

export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const [activeIdx, setActiveIdx] = useState(0);
  const navigate = useNavigate();

  // Keyboard listener — Cmd/Ctrl+K toggles; Escape closes.
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const isToggle = (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k';
      if (isToggle) {
        e.preventDefault();
        setOpen((o) => !o);
        setQ('');
        setActiveIdx(0);
        return;
      }
      if (open && e.key === 'Escape') {
        e.preventDefault();
        setOpen(false);
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open]);

  // Lazy-load the index when the palette opens.
  const { data: subcaps } = useQuery<SubcapRow[]>({
    queryKey: ['palette-subcaps'],
    queryFn: () => apiGet<SubcapRow[]>('/catalogue/subcaps'),
    enabled: open,
    staleTime: 5 * 60 * 1000,
  });
  const { data: l3s } = useQuery<L3Row[]>({
    queryKey: ['palette-l3s'],
    queryFn: () => apiGet<L3Row[]>('/catalogue/l3-platforms'),
    enabled: open,
    staleTime: 5 * 60 * 1000,
  });
  const { data: chains } = useQuery<ChainRow[]>({
    queryKey: ['palette-chains'],
    queryFn: () => apiGet<ChainRow[]>('/reasoning-chains?limit=50'),
    enabled: open,
    staleTime: 60 * 1000,
  });

  const index = useMemo<CommandItem[]>(() => {
    const out: CommandItem[] = [...STATIC_PAGES];
    for (const s of subcaps || []) {
      out.push({
        id: `s:${s.sub_cap_id}`,
        label: `${s.sub_cap_id} — ${s.sub_cap_name}`,
        subtitle: s.pillar_id,
        kind: 'subcap',
        to: `/subcap?id=${encodeURIComponent(s.sub_cap_id)}`,
      });
    }
    for (const l of l3s || []) {
      out.push({
        id: `l:${l.l3_id}`,
        label: `${l.l3_id} — ${l.name}`,
        subtitle: l.vendor,
        kind: 'l3',
        to: `/platforms?id=${encodeURIComponent(l.l3_id)}`,
      });
    }
    for (const c of chains || []) {
      out.push({
        id: `c:${c.chain_id}`,
        label: c.chain_id,
        subtitle: `${c.operation || 'chain'}${c.sub_cap_id ? ` · ${c.sub_cap_id}` : ''}`,
        kind: 'chain',
        to: `/reasoning?id=${encodeURIComponent(c.chain_id)}`,
      });
    }
    return out;
  }, [subcaps, l3s, chains]);

  const results = useMemo(() => {
    if (!q.trim()) return STATIC_PAGES;
    const scored = index
      .map((it) => ({ it, score: scoreMatch(q, `${it.label} ${it.subtitle || ''}`) }))
      .filter((r) => r.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, MAX_RESULTS)
      .map((r) => r.it);
    return scored;
  }, [q, index]);

  useEffect(() => {
    if (activeIdx >= results.length) setActiveIdx(0);
  }, [results, activeIdx]);

  function commit(item: CommandItem) {
    setOpen(false);
    setQ('');
    navigate(item.to);
  }

  function onInputKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIdx((i) => (i + 1) % Math.max(1, results.length));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIdx((i) =>
        i === 0 ? Math.max(0, results.length - 1) : i - 1,
      );
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const item = results[activeIdx];
      if (item) commit(item);
    }
  }

  if (!open) return null;
  const loading = !subcaps && !l3s && !chains;
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="command-palette-title"
      className="fixed inset-0 z-50 flex items-start justify-center bg-zen-dark-green/40 backdrop-blur-sm pt-24 px-4"
      onClick={() => setOpen(false)}
    >
      <div
        className="w-full max-w-xl rounded-lg bg-white border border-zen-separator shadow-lg overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 px-3 py-2 border-b border-zen-separator">
          <Search size={16} className="text-zen-dark-teal/70" />
          <input
            type="text"
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={onInputKeyDown}
            placeholder="Search subcaps, platforms, chains, pages…"
            aria-label="command palette search"
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-zen-dark-teal/40 text-zen-dark-green"
          />
          {loading && <Loader2 size={14} className="animate-spin text-zen-teal" />}
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label="close command palette"
            className="text-zen-dark-teal/60 hover:text-zen-dark-green p-1"
          >
            <X size={14} />
          </button>
        </div>
        <div id="command-palette-title" className="sr-only">
          Command palette — Cmd/Ctrl+K to open, Escape to close
        </div>
        <ul role="listbox" className="max-h-[60vh] overflow-auto">
          {results.length === 0 && (
            <li className="px-3 py-4 text-sm text-zen-dark-teal/70">
              No matches. Try a subcap id (P1C1.1.1), L3 id (L3-SF-FSC), or page name.
            </li>
          )}
          {results.map((item, i) => (
            <li
              key={item.id}
              role="option"
              aria-selected={i === activeIdx}
              onMouseEnter={() => setActiveIdx(i)}
              onClick={() => commit(item)}
              className={`px-3 py-2 cursor-pointer text-sm flex items-center justify-between gap-3 ${
                i === activeIdx
                  ? 'bg-zen-light-green/50 text-zen-dark-green'
                  : 'text-zen-dark-teal hover:bg-zen-ice'
              }`}
            >
              <div className="min-w-0 flex-1">
                <div className="truncate">{item.label}</div>
                {item.subtitle && (
                  <div className="text-[10px] text-zen-dark-teal/60 truncate">{item.subtitle}</div>
                )}
              </div>
              <span className="text-[9px] uppercase tracking-wider text-zen-dark-teal/50 shrink-0">
                {item.kind}
              </span>
            </li>
          ))}
        </ul>
        <div className="px-3 py-1.5 border-t border-zen-separator text-[10px] text-zen-dark-teal/60 flex items-center justify-between">
          <span>↑↓ navigate · ↵ select · Esc close</span>
          <span>Cmd+K toggles</span>
        </div>
      </div>
    </div>
  );
}
