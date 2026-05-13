import { Bell, Loader2, Search, User } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { apiPost } from '../lib/api';

export default function Header() {
  const [busy, setBusy] = useState(false);
  const [last, setLast] = useState<{
    sources_succeeded: number;
    sources_total: number;
    failures: string[];
  } | null>(null);

  async function pullAll() {
    setBusy(true);
    setLast(null);
    try {
      const r = await apiPost<{
        sources_succeeded: number;
        sources_failed: number;
        sources_total: number;
        results: { ok: boolean; source: string; error?: string }[];
      }>('/ingest/refresh-all', {});
      setLast({
        sources_succeeded: r.sources_succeeded,
        sources_total: r.sources_total,
        failures: r.results.filter((x) => !x.ok).map((x) => `${x.source}: ${x.error}`),
      });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setLast({ sources_succeeded: 0, sources_total: 0, failures: [`request: ${msg}`] });
    } finally {
      setBusy(false);
    }
  }

  return (
    <header
      data-testid="header"
      className="h-14 shrink-0 bg-white border-b border-zen-light-green/50 flex items-center px-6 gap-4"
    >
      <div className="flex items-center gap-2 flex-1 max-w-xl">
        <Search size={16} className="text-zen-dark-teal/60" />
        <input
          type="text"
          placeholder="Search subcaps, vendors, clients, news…"
          className="w-full bg-transparent text-sm outline-none placeholder:text-zen-dark-teal/50"
          aria-label="global search"
        />
      </div>

      <div className="flex items-center gap-2 text-xs text-zen-dark-teal">
        <span className="bg-zen-light-green/40 rounded-full px-2 py-0.5">Persona: Senior Partner</span>
        <span className="bg-zen-light-green/40 rounded-full px-2 py-0.5">All subverticals</span>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={pullAll}
          disabled={busy}
          aria-label="pull all sources"
          className="bg-zen-teal hover:bg-zen-dark-teal text-white text-xs font-medium px-3 py-1.5 rounded transition-colors duration-200 disabled:opacity-60 flex items-center gap-1"
        >
          {busy && <Loader2 size={12} className="animate-spin" />}
          {busy ? 'Pulling…' : 'Pull all sources'}
        </button>
        {last && (
          <span
            className="text-xs text-zen-dark-teal/70"
            title={last.failures.join('\n')}
            aria-live="polite"
          >
            {last.sources_succeeded}/{last.sources_total} ok
          </span>
        )}
      </div>

      <button type="button" aria-label="notifications" className="text-zen-dark-teal/70 hover:text-zen-dark-teal">
        <Bell size={18} />
      </button>

      <Link
        to="/settings"
        aria-label="user menu / settings"
        className="flex items-center gap-2 text-sm text-zen-dark-teal hover:text-zen-dark-green"
      >
        <User size={18} />
        <span>dev@zennify.com</span>
      </Link>
    </header>
  );
}
