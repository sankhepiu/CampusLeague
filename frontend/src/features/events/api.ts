import { env } from '../../core/config/env';
import { mockEventsApi } from './api.mock';
import { realEventsApi } from './api.real';

/** Same typed surface regardless of mode — components never branch on env.useMockApi. */
export const eventsApi = env.useMockApi ? mockEventsApi : realEventsApi;

export type { Attendance, EventDetail, EventDraft, EventItem, EventStatus, Pnl, Tier, TierDraft } from './types';
