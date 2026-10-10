import { request, session } from '../../api/client';
import type { AuthUser, LoginRequest, LoginResponse, SignupRequest, SignupResponse } from './types';

export const realAuthApi = {
  async login(body: LoginRequest): Promise<AuthUser> {
    const result = await request<LoginResponse>('/auth/login', { method: 'POST', body });
    session.setToken(result.token);
    return result.user;
  },

  async signup(body: SignupRequest): Promise<AuthUser> {
    const result = await request<SignupResponse>('/auth/signup', { method: 'POST', body });
    session.setToken(result.token);
    return result.user;
  },

  async me(): Promise<AuthUser> {
    return request<AuthUser>('/auth/me');
  },

  async logout(): Promise<void> {
    try {
      await request<void>('/auth/logout', { method: 'POST' });
    } finally {
      session.clearToken();
    }
  },
};
