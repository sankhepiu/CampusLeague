import { env } from '../../core/config/env';
import { mockVolunteeringApi } from './api.mock';
import { realVolunteeringApi } from './api.real';

/** Same typed surface regardless of mode — components never branch on env.useMockApi. */
export const volunteeringApi = env.useMockApi ? mockVolunteeringApi : realVolunteeringApi;

export type { AssignRequest, Fundraiser, FundraiserDraft, FundraiserStatus, SaleRequest, Task, TaskDraft, TaskStatus } from './types';
