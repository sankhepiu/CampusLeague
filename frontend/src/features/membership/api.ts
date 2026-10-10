import { env } from '../../core/config/env';
import { mockMembershipApi } from './api.mock';
import { realMembershipApi } from './api.real';

/** Same typed surface regardless of mode — components never branch on env.useMockApi. */
export const membershipApi = env.useMockApi ? mockMembershipApi : realMembershipApi;

export type { MembershipRecord, MembershipRecordStatus, MyMembership, Plan, PurchaseRequest, PurchaseResult } from './types';
