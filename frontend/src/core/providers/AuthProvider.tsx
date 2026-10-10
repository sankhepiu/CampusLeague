import { createContext, useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { setUnauthorizedHandler, type ApiError } from '../../api/client';
import { authApi } from '../../features/auth/api';
import type { AuthUser, SignupRequest } from '../../features/auth/types';
import type { Role } from '../config/roles';

type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated' | 'error';

interface AuthContextValue {
  status: AuthStatus;
  user: AuthUser | null;
  error: ApiError | null;
  login: (email: string, password: string) => Promise<void>;
  signup: (data: SignupRequest) => Promise<void>;
  logout: () => Promise<void>;
  hasRole: (...roles: Role[]) => boolean;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading');
  const [user, setUser] = useState<AuthUser | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const becomeUnauthenticated = useCallback(() => {
    setUser(null);
    setStatus('unauthenticated');
  }, []);

  // Hydrate the session once on load. Runs exactly once, so there is no
  // repeated redirect loop between the guard and this effect.
  useEffect(() => {
    let cancelled = false;
    authApi
      .me()
      .then((authUser) => {
        if (cancelled) return;
        setUser(authUser);
        setStatus('authenticated');
      })
      .catch(() => {
        if (cancelled) return;
        becomeUnauthenticated();
      });
    return () => {
      cancelled = true;
    };
  }, [becomeUnauthenticated]);

  useEffect(() => {
    setUnauthorizedHandler(becomeUnauthenticated);
    return () => setUnauthorizedHandler(null);
  }, [becomeUnauthenticated]);

  const login = useCallback(async (email: string, password: string) => {
    setStatus('loading');
    setError(null);
    try {
      const authUser = await authApi.login({ email, password });
      setUser(authUser);
      setStatus('authenticated');
    } catch (err) {
      setError(err as ApiError);
      setStatus('unauthenticated');
      throw err;
    }
  }, []);

  const signup = useCallback(async (data: SignupRequest) => {
    setStatus('loading');
    setError(null);
    try {
      // The request only ever carries what the server needs — no role field
      // exists on SignupRequest, so there is nothing client-side to strip.
      const authUser = await authApi.signup(data);
      setUser(authUser);
      setStatus('authenticated');
    } catch (err) {
      setError(err as ApiError);
      setStatus('unauthenticated');
      throw err;
    }
  }, []);

  const logout = useCallback(async () => {
    await authApi.logout();
    becomeUnauthenticated();
  }, [becomeUnauthenticated]);

  const hasRole = useCallback((...roles: Role[]) => !!user && roles.some((r) => user.roles.includes(r)), [user]);

  const value = useMemo<AuthContextValue>(
    () => ({ status, user, error, login, signup, logout, hasRole }),
    [status, user, error, login, signup, logout, hasRole],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
