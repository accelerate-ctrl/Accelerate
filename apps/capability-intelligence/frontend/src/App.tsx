import Sidebar from './components/Sidebar';
import Header from './components/Header';
import AppRoutes from './routes';

export default function App() {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-zen-white-green">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-auto p-6">
          <AppRoutes />
        </main>
      </div>
    </div>
  );
}
