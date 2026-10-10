import type { Role } from '../../core/config/roles';

export interface RoleAssignment {
  id: number;
  user: number;
  role: Role;
  termStart: string; // YYYY-MM-DD
  termEnd: string;
  createdAt: string;
}

export interface RoleAssignmentDraft {
  user: number;
  role: Role;
  termStart: string;
  termEnd: string;
}

export interface AuditActor {
  id: number;
  name: string;
}

export interface AuditLogItem {
  id: number;
  actor: AuditActor | null;
  action: string;
  objectType: string;
  objectId: number;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  at: string;
}

export interface AuditLogParams {
  action?: string;
}
