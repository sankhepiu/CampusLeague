import { request, type Paginated } from '../../api/client';
import type { Announcement, AnnouncementDraft, DeliveryLogEntry } from './types';

interface WireAnnouncement {
  id: number;
  title: string;
  body: string;
  audience: Announcement['audience'];
  author: { id: number; name: string };
  published_at: string;
  deliveries: Announcement['deliveries'];
}

interface WireDeliveryLogEntry {
  id: number;
  recipient: { id: number; name: string; email: string };
  status: DeliveryLogEntry['status'];
  attempts: number;
  last_error: string | null;
  updated_at: string;
}

function fromWireAnnouncement(a: WireAnnouncement): Announcement {
  return { id: a.id, title: a.title, body: a.body, audience: a.audience, author: a.author, publishedAt: a.published_at, deliveries: a.deliveries };
}

function fromWireDelivery(d: WireDeliveryLogEntry): DeliveryLogEntry {
  return { id: d.id, recipient: d.recipient, status: d.status, attempts: d.attempts, lastError: d.last_error, updatedAt: d.updated_at };
}

export const realAnnouncementsApi = {
  async list(page = 1): Promise<Paginated<Announcement>> {
    const result = await request<Paginated<WireAnnouncement>>('/announcements', { query: { page } });
    return { ...result, results: result.results.map(fromWireAnnouncement) };
  },

  async get(id: number): Promise<Announcement> {
    return fromWireAnnouncement(await request<WireAnnouncement>(`/announcements/${id}`));
  },

  async create(draft: AnnouncementDraft): Promise<Announcement> {
    return fromWireAnnouncement(
      await request<WireAnnouncement>('/announcements', {
        method: 'POST',
        body: { title: draft.title, body: draft.body, ...(draft.audience ? { audience: draft.audience } : {}) },
      }),
    );
  },

  async listDeliveries(id: number, page = 1): Promise<Paginated<DeliveryLogEntry>> {
    const result = await request<Paginated<WireDeliveryLogEntry>>(`/announcements/${id}/deliveries`, { query: { page } });
    return { ...result, results: result.results.map(fromWireDelivery) };
  },
};
