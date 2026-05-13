import { NavLink } from 'react-router-dom';
import { X } from 'lucide-react';
import { navigation } from '../lib/sidebar-config';
import fullLight from '../assets/zennify/full_light.png';

type Props = {
  mobileOpen?: boolean;
  onCloseMobile?: () => void;
};

export default function Sidebar({ mobileOpen = false, onCloseMobile }: Props) {
  return (
    <aside
      data-testid="sidebar"
      className={[
        'w-72 shrink-0 bg-zen-dark-green text-white flex flex-col overflow-y-auto z-40',
        // Mobile: off-canvas drawer
        'fixed inset-y-0 left-0 transition-transform duration-300 md:static md:translate-x-0',
        mobileOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0',
      ].join(' ')}
    >
      <div className="p-5 border-b border-white/10 flex items-center justify-between">
        <img
          src={fullLight}
          alt="Zennify"
          // 1653×589 → cap to 32px height to match a typical app header.
          className="h-8 w-auto"
        />
        {onCloseMobile && (
          <button
            type="button"
            aria-label="close menu"
            onClick={onCloseMobile}
            className="md:hidden text-white/70 hover:text-white"
          >
            <X size={18} />
          </button>
        )}
      </div>
      <div className="px-5 pt-3 text-white/60 text-xs">Capability Intelligence</div>
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
                    onClick={onCloseMobile}
                    className={({ isActive }) =>
                      `flex items-center rounded px-2 py-1.5 text-sm transition-colors duration-200 ${
                        isActive
                          ? 'bg-zen-teal/25 text-white'
                          : 'text-white/80 hover:bg-white/5 hover:text-white'
                      }`
                    }
                  >
                    <span>{entry.label}</span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>
      <div className="p-3 text-[10px] text-white/40 border-t border-white/10">v0.1.0</div>
    </aside>
  );
}
