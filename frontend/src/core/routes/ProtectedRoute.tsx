import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import type { Role } from '../config/roles';
import { Spinner } from '../../components/Spinner/Spinner';
import { UnauthorizedScreen } from './UnauthorizedScreen';

interface ProtectedRouteProps {
  roles?: Role[] | null;
  children: ReactNode;
}

/** Gates a route on authentication, and optionally on role membership.
 * Renders a spinner while the session is still being resolved so an
 * unauthenticated flash never causes a redirect loop on first load. */
export function ProtectedRoute({ roles, children }: ProtectedRouteProps) {
  const { status, user, hasRole } = useAuth();
  const location = useLocation();

  if (status === 'loading') {
    return <Spinner fullPage label="Checking your session…" />;
  }

  if (status !== 'authenticated' || !user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  if (roles && roles.length > 0 && !hasRole(...roles)) {
    return <UnauthorizedScreen />;
  }

  return <>{children}</>;
}
