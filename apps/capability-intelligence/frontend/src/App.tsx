import { useEffect, useState } from 'react';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import SignInGate from './components/SignInGate';
import AppRoutes from './routes';
import { useAuth } from './lib/auth';

export default function App() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const load = useAuth((s) => s.load);

  // Boot — discover auth_mode + restore any prior GIS session.
  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-surface text-fg">
      <SignInGate />
      <Sidebar mobileOpen={drawerOpen} onCloseMobile={() => setDrawerOpen(false)} />
      {drawerOpen && (
        <button
          type="button"
          aria-label="close menu"
          onClick={() => setDrawerOpen(false)}
          className="md:hidden fixed inset-0 bg-zen-dark-green/40 z-30"
        />
      )}
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header onOpenMobileMenu={() => setDrawerOpen(true)} />
        <main className="flex-1 overflow-auto p-4 md:p-6">
          <AppRoutes />
        </main>
      </div>
    </div>
  );
}
