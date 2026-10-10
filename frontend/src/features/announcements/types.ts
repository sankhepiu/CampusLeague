export type Audience = 'all' | 'members';

export interface DeliverySummary {
  recipients: number;
  queued: number;
  sent: number;
  failed: number;
}

export interface Announcement {
  id: number;
  title: string;
  body: string;
  audience: Audience;
  author: { id: number; name: string };
  publishedAt: string;
  /** null for everyone except president/event_manager/volunteer_coordinator. */
  deliveries: DeliverySummary | null;
}

export interface AnnouncementDraft {
  title: string;
  body: string;
  audience?: Audience;
}

export type DeliveryStatus = 'queued' | 'sent' | 'failed';

export interface DeliveryLogEntry {
  id: number;
  recipient: { id: number; name: string; email: string };
  status: DeliveryStatus;
  attempts: number;
  lastError: string | null;
  updatedAt: string;
}
