import { request, session } from '../../api/client';
import type { AuthResponse, AuthUser, LoginRequest, SignupRequest, SignupResult, VerifyEmailRequest } from './types';

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

  /** Creates the account and has the server email a 6-digit code. There is
   * no token yet, so nothing is stored in the session here. */
  async signup({ email, password, name, collegeId, phone }: SignupRequest): Promise<SignupResult> {
    const result = await request<{ verification_required: true; email: string }>('/auth/signup', {
      method: 'POST',
      body: { email, password, name, college_id: collegeId, ...(phone ? { phone } : {}) },
    });
    return { verificationRequired: true, email: result.email };
  },

  /** Confirms the emailed code. The response is exactly a login response,
   * so on success the user is signed in. Errors (as `ApiRequestError.code`):
   * `invalid_code`, `code_expired`, `too_many_attempts`, `throttled`. */
  async verifyEmail({ email, code }: VerifyEmailRequest): Promise<AuthUser> {
    const result = fromWireAuth(await request<WireAuthResponse>('/auth/verify-email', { method: 'POST', body: { email, code } }));
    session.setToken(result.token);
    return result.user;
  },

  /** Always resolves: the server answers `{sent: true}` whether or not the
   * address has an account, and silently sends at most one code per 60
   * seconds, so the UI must run its own 60-second cooldown. */
  async resendCode(email: string): Promise<void> {
    await request<{ sent: true }>('/auth/resend-code', { method: 'POST', body: { email } });
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
