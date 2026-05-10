import { Bell, Search, User } from 'lucide-react';

export default function Header() {
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

      <button
        type="button"
        aria-label="pull all sources"
        className="bg-zen-teal hover:bg-zen-dark-teal text-white text-xs font-medium px-3 py-1.5 rounded transition-colors duration-200"
      >
        Pull all sources
      </button>

      <button type="button" aria-label="notifications" className="text-zen-dark-teal/70 hover:text-zen-dark-teal">
        <Bell size={18} />
      </button>

      <button
        type="button"
        aria-label="user menu"
        className="flex items-center gap-2 text-sm text-zen-dark-teal hover:text-zen-dark-green"
      >
        <User size={18} />
        <span>dev@zennify.com</span>
      </button>
    </header>
  );
}
