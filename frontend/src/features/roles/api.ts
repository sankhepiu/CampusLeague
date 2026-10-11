import { env } from '../../core/config/env';
import { mockRolesApi } from './api.mock';
import { realRolesApi } from './api.real';

/** Same typed surface regardless of mode — components never branch on env.useMockApi. */
export const rolesApi = env.useMockApi ? mockRolesApi : realRolesApi;

export type { InviteStatus, ListInvitesParams, RoleInvite, RoleInviteDraft } from './types';
