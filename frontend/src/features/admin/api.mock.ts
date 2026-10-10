import type { Paginated } from '../../api/client';
import { mockAdmin } from './mockAdminStore';
import type { AuditLogItem, AuditLogParams, RoleAssignment, RoleAssignmentDraft } from './types';

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const PAGE_SIZE = 20;

function paginate<T>(items: T[], page: number): Paginated<T> {
  const start = (page - 1) * PAGE_SIZE;
  const results = items.slice(start, start + PAGE_SIZE);
  return { count: items.length, next: start + PAGE_SIZE < items.length ? `?page=${page + 1}` : null, previous: page > 1 ? `?page=${page - 1}` : null, results };
}

export const mockAdminApi = {
  async listRoles(page = 1): Promise<Paginated<RoleAssignment>> {
    await delay(300);
    return paginate(mockAdmin.listRoles(), page);
  },

  async assignRole(draft: RoleAssignmentDraft): Promise<RoleAssignment> {
    await delay(400);
    return mockAdmin.assignRole(draft);
  },

  async listAuditLog(params: AuditLogParams = {}, page = 1): Promise<Paginated<AuditLogItem>> {
    await delay(300);
    return paginate(mockAdmin.listAuditLog(params.action), page);
  },
};
