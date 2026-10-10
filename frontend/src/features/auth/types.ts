import type { Role } from '../../core/config/roles';

export type MembershipStatus = 'active' | 'lapsed' | 'none';

/** Matches the contract's "User object" exactly (snake_case fields as the
 * wire shape; the api layer below maps to/from this). */
export interface AuthUser {
  id: number;
  email: string;
  name: string;
  collegeId: string;
  phone: string;
  roles: Role[];
  membershipStatus: MembershipStatus;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface SignupRequest {
  email: string;
  password: string;
  name: string;
  collegeId: string;
  phone?: string;
}

export interface AuthResponse {
  token: string;
  user: AuthUser;
}
