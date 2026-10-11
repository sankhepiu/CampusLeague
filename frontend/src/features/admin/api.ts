import { env } from '../../core/config/env';
import { mockAdminApi } from './api.mock';
import { realAdminApi } from './api.real';

/** Same typed surface regardless of mode — components never branch on env.useMockApi. */
export const adminApi = env.useMockApi ? mockAdminApi : realAdminApi;

export type { AuditActor, AuditLogItem, AuditLogParams, RoleAssignment } from './types';
