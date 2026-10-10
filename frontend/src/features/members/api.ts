import { env } from '../../core/config/env';
import { mockMembersApi } from './api.mock';
import { realMembersApi } from './api.real';

/** Same typed surface regardless of mode — components never branch on env.useMockApi. */
export const membersApi = env.useMockApi ? mockMembersApi : realMembersApi;

export type { ListMembersParams, MemberSummary } from './types';
