import { Outlet } from 'react-router-dom';
import { TopBar } from '../../components/TopBar/TopBar';
import { Footer } from '../../components/Footer/Footer';
import { InviteBanner } from '../../features/roles/InviteBanner';
import { RouteTransition } from './RouteTransition';

export function AppLayout() {
  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <TopBar />
      <InviteBanner />
      <main style={{ flex: 1 }}>
        <RouteTransition>
          <Outlet />
        </RouteTransition>
      </main>
      <Footer />
    </div>
  );
}
