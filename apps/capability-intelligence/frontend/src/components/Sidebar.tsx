import { NavLink } from 'react-router-dom';
import { navigation } from '../lib/sidebar-config';

export default function Sidebar() {
  return (
    <aside
      data-testid="sidebar"
      className="w-72 shrink-0 bg-zen-dark-green text-white flex flex-col overflow-y-auto"
    >
      <div className="p-5 border-b border-white/10">
        <div className="text-zen-light-teal font-semibold text-lg leading-tight">Zennify</div>
        <div className="text-white/70 text-xs mt-0.5">Capability Intelligence</div>
      </div>
      <nav className="flex-1 p-3 space-y-5">
        {navigation.map((group) => (
          <div key={group.label}>
            <div className="text-[10px] font-semibold tracking-widest uppercase text-zen-light-teal/70 px-2 mb-1">
              {group.label}
            </div>
            <ul className="space-y-0.5">
              {group.entries.map((entry) => (
                <li key={entry.path}>
                  <NavLink
                    to={entry.path}
                    end={entry.path === '/'}
                    className={({ isActive }) =>
                      `flex items-center justify-between rounded px-2 py-1.5 text-sm transition-colors duration-200 ${
                        isActive
                          ? 'bg-zen-teal/20 text-white'
                          : 'text-white/80 hover:bg-white/5 hover:text-white'
                      }`
                    }
                  >
                    <span>{entry.label}</span>
                    <span className="text-[9px] uppercase tracking-widest text-zen-light-teal/60">
                      B{entry.batch}
                    </span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>
      <div className="p-3 text-[10px] text-white/40 border-t border-white/10">v0.1.0 · Batch 0</div>
    </aside>
  );
}
