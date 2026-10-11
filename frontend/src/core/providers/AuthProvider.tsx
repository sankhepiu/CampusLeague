import { createContext, useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { setUnauthorizedHandler, type ApiError } from '../../api/client';
import { authApi } from '../../features/auth/api';
import type { AuthUser, SignupRequest, SignupResult } from '../../features/auth/types';
import type { Role } from '../config/roles';

type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated' | 'error';

interface AuthContextValue {
  status: AuthStatus;
  user: AuthUser | null;
  error: ApiError | null;
  login: (email: string, password: string, club?: string) => Promise<void>;
  /** Creates the account. Does NOT sign in: the email must be verified. */
  signup: (data: SignupRequest) => Promise<SignupResult>;
  /** Confirms the emailed code and signs the user in. */
  verifyEmail: (email: string, code: string) => Promise<void>;
  resendCode: (email: string) => Promise<void>;
  logout: () => Promise<void>;
  hasRole: (...roles: Role[]) => boolean;
  /** Re-fetches the current user — used after accepting a role invite, so
   * the new nav/access shows up immediately instead of waiting for the
   * next login. */
  refreshUser: () => Promise<void>;
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

  const login = useCallback(async (email: string, password: string, club?: string) => {
    setStatus('loading');
    setError(null);
    try {
      const authUser = await authApi.login({ email, password, ...(club ? { club } : {}) });
      setUser(authUser);
      setStatus('authenticated');
    } catch (err) {
      setError(err as ApiError);
      setStatus('unauthenticated');
      throw err;
    }
  }, []);

  // Signup creates an unverified account and returns no token, so the auth
  // status does not change here: the visitor stays signed out until
  // verifyEmail succeeds. The request only ever carries what the server
  // needs — no role field exists on SignupRequest.
  const signup = useCallback((data: SignupRequest) => authApi.signup(data), []);

  const verifyEmail = useCallback(async (email: string, code: string) => {
    const authUser = await authApi.verifyEmail({ email, code });
    setError(null);
    setUser(authUser);
    setStatus('authenticated');
  }, []);

  const resendCode = useCallback((email: string) => authApi.resendCode(email), []);

  const logout = useCallback(async () => {
    await authApi.logout();
    becomeUnauthenticated();
  }, [becomeUnauthenticated]);

  const hasRole = useCallback((...roles: Role[]) => !!user && roles.some((r) => user.roles.includes(r)), [user]);

  const refreshUser = useCallback(async () => {
    try {
      setUser(await authApi.me());
    } catch {
      /* session may have just ended elsewhere; the 401 handler covers that */
    }
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ status, user, error, login, signup, verifyEmail, resendCode, logout, hasRole, refreshUser }),
    [status, user, error, login, signup, verifyEmail, resendCode, logout, hasRole, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
