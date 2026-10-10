import { env } from '../../core/config/env';
import { mockAnnouncementsApi } from './api.mock';
import { realAnnouncementsApi } from './api.real';

/** Same typed surface regardless of mode — components never branch on env.useMockApi. */
export const announcementsApi = env.useMockApi ? mockAnnouncementsApi : realAnnouncementsApi;

export type { Announcement, AnnouncementDraft, Audience, DeliveryLogEntry, DeliverySummary } from './types';
