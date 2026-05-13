import { useState } from 'react';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import AppRoutes from './routes';

export default function App() {
  const [drawerOpen, setDrawerOpen] = useState(false);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-zen-ice">
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
