import { Outlet } from 'react-router-dom';
import { TopBar } from '../../components/TopBar/TopBar';
import { Footer } from '../../components/Footer/Footer';
import { RouteTransition } from './RouteTransition';

export function AppLayout() {
  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <TopBar />
      <main style={{ flex: 1 }}>
        <RouteTransition>
          <Outlet />
        </RouteTransition>
      </main>
      <Footer />
    </div>
  );
}
