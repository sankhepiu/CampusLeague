import { request, session } from '../../api/client';
import type { AuthResponse, AuthUser, LoginRequest, SignupRequest } from './types';

/** Wire shapes exactly as docs/API_CONTRACT.md defines them (snake_case). */
interface WireUser {
  id: number;
  email: string;
  name: string;
  college_id: string;
  phone: string;
  roles: AuthUser['roles'];
  membership_status: AuthUser['membershipStatus'];
}

interface WireAuthResponse {
  token: string;
  user: WireUser;
}

function fromWireUser(u: WireUser): AuthUser {
  return {
    id: u.id,
    email: u.email,
    name: u.name,
    collegeId: u.college_id,
    phone: u.phone,
    roles: u.roles,
    membershipStatus: u.membership_status,
  };
}

function fromWireAuth(res: WireAuthResponse): AuthResponse {
  return { token: res.token, user: fromWireUser(res.user) };
}

export const realAuthApi = {
  async login(body: LoginRequest): Promise<AuthUser> {
    const result = fromWireAuth(await request<WireAuthResponse>('/auth/login', { method: 'POST', body }));
    session.setToken(result.token);
    return result.user;
  },

  async signup({ email, password, name, collegeId, phone }: SignupRequest): Promise<AuthUser> {
    const result = fromWireAuth(
      await request<WireAuthResponse>('/auth/signup', {
        method: 'POST',
        body: { email, password, name, college_id: collegeId, ...(phone ? { phone } : {}) },
      }),
    );
    session.setToken(result.token);
    return result.user;
  },

  async me(): Promise<AuthUser> {
    return fromWireUser(await request<WireUser>('/auth/me'));
  },

  async logout(): Promise<void> {
    try {
      await request<void>('/auth/logout', { method: 'POST' });
    } finally {
      session.clearToken();
    }
  },
};
