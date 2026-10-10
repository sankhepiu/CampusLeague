import type { Role } from '../../core/config/roles';

export interface AuthUser {
  id: string;
  name: string;
  email: string;
  roles: Role[];
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  token: string;
  user: AuthUser;
}

export interface SignupRequest {
  name: string;
  email: string;
  collegeId: string;
  password: string;
}

export interface SignupResponse {
  token: string;
  user: AuthUser;
}
