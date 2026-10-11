import { request, type Paginated } from '../../api/client';
import type { AuditActor, AuditLogItem, AuditLogParams, RoleAssignment } from './types';

interface WireRoleAssignment {
  id: number;
  user: number;
  role: RoleAssignment['role'];
  term_start: string;
  term_end: string;
  created_at: string;
}

function fromWireRoleAssignment(r: WireRoleAssignment): RoleAssignment {
  return { id: r.id, user: r.user, role: r.role, termStart: r.term_start, termEnd: r.term_end, createdAt: r.created_at };
}

interface WireAuditLogItem {
  id: number;
  actor: AuditActor | null;
  action: string;
  object_type: string;
  object_id: number;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  at: string;
}

function fromWireAuditLogItem(a: WireAuditLogItem): AuditLogItem {
  return { id: a.id, actor: a.actor, action: a.action, objectType: a.object_type, objectId: a.object_id, before: a.before, after: a.after, at: a.at };
}

export const realAdminApi = {
  async listRoles(page = 1): Promise<Paginated<RoleAssignment>> {
    const result = await request<Paginated<WireRoleAssignment>>('/roles', { query: { page } });
    return { ...result, results: result.results.map(fromWireRoleAssignment) };
  },

  // GET /audit, as documented in docs/API_CONTRACT.md (president only).
  async listAuditLog(params: AuditLogParams = {}, page = 1): Promise<Paginated<AuditLogItem>> {
    const result = await request<Paginated<WireAuditLogItem>>('/audit', { query: { page, action: params.action } });
    return { ...result, results: result.results.map(fromWireAuditLogItem) };
  },
};
