import { env } from '../../core/config/env';
import { mockAuthApi } from './api.mock';
import { realAuthApi } from './api.real';

/** Same typed surface regardless of mode — components never branch on env.useMockApi. */
export const authApi = env.useMockApi ? mockAuthApi : realAuthApi;

export type { AuthResponse, AuthUser, LoginRequest, MembershipStatus, SignupRequest } from './types';
