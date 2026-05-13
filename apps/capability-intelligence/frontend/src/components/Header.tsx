import { Loader2, LogOut, Menu, Search } from 'lucide-react';
import { useState } from 'react';
import { apiPost } from '../lib/api';
import { useAuth } from '../lib/auth';
import { SUBVERTICALS, useFilters } from '../store/filters';
import iconTeal from '../assets/zennify/icon_teal.png';

type Props = {
  onOpenMobileMenu?: () => void;
};

export default function Header({ onOpenMobileMenu }: Props) {
  const { subverticalCode, setSubvertical, search, setSearch } = useFilters();
  const { email, token, signOut } = useAuth();
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
      className="h-14 shrink-0 bg-white border-b border-zen-separator flex items-center px-3 md:px-6 gap-2 md:gap-4"
    >
      {/* Mobile hamburger */}
      <button
        type="button"
        aria-label="open menu"
        onClick={onOpenMobileMenu}
        className="md:hidden text-zen-dark-green p-1 -ml-1"
      >
        <Menu size={20} />
      </button>

      {/* Chevron icon (icon_teal.png from ZDS) — branded anchor */}
      <img src={iconTeal} alt="" className="hidden md:block w-7 h-7" />

      {/* Search */}
      <div className="flex items-center gap-2 flex-1 max-w-xl">
        <Search size={16} className="text-zen-muted-text" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search subcaps, vendors, clients, news…"
          className="w-full bg-transparent text-sm outline-none placeholder:text-zen-muted-text"
          aria-label="global search"
        />
      </div>

      {/* Subvertical filter — real dropdown driven by the filter store */}
      <select
        value={subverticalCode ?? ''}
        onChange={(e) => setSubvertical(e.target.value || null)}
        aria-label="subvertical filter"
        className="hidden sm:block text-xs bg-zen-ice text-zen-dark-green rounded px-2 py-1 border border-zen-separator focus:outline-none focus:ring-1 focus:ring-zen-teal"
      >
        <option value="">All subverticals</option>
        {SUBVERTICALS.map((s) => (
          <option key={s.code} value={s.code}>{s.label}</option>
        ))}
      </select>

      {/* Pull-all-sources */}
      <button
        type="button"
        onClick={pullAll}
        disabled={busy}
        aria-label="pull all sources"
        className="bg-zen-teal hover:bg-zen-dark-teal text-white text-xs font-medium px-3 py-1.5 rounded transition-colors duration-200 disabled:opacity-60 flex items-center gap-1 whitespace-nowrap"
      >
        {busy && <Loader2 size={12} className="animate-spin" />}
        {busy ? 'Pulling…' : 'Pull sources'}
      </button>
      {last && (
        <span
          className="hidden lg:inline text-xs text-zen-muted-text"
          title={last.failures.join('\n')}
          aria-live="polite"
        >
          {last.sources_succeeded}/{last.sources_total} ok
        </span>
      )}

      {/* Sign-out — only shown when an actual Google ID-token session is
          active. Dev-mode users don't see a sign-out button (no session
          to end). */}
      {token && email && (
        <button
          type="button"
          onClick={signOut}
          className="hidden md:inline-flex items-center gap-1 text-xs text-zen-text-gray hover:text-zen-dark-green border border-transparent hover:border-zen-separator rounded px-2 py-1"
          title={`Signed in as ${email}`}
        >
          <LogOut size={12} />
          <span className="max-w-[120px] truncate">{email}</span>
        </button>
      )}
    </header>
  );
}
