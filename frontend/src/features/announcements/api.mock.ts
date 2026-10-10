import { ApiRequestError, type Paginated } from '../../api/client';
import { getCurrentMockUser, listAllUsers } from '../auth/mockUsers';
import type { Announcement, AnnouncementDraft, DeliveryLogEntry, DeliverySummary } from './types';

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const PAGE_SIZE = 20;
const COMPOSER_ROLES = ['president', 'event_manager', 'volunteer_coordinator'];

interface StoredAnnouncement extends Omit<Announcement, 'deliveries'> {
  deliveries: DeliverySummary;
}

interface StoredDeliveryLog {
  announcementId: number;
  entries: DeliveryLogEntry[];
}

const STORE_KEY = 'campusleague.mock.announcements';
const LOG_KEY = 'campusleague.mock.announcementDeliveries';

function seedAnnouncements(): StoredAnnouncement[] {
  return [
    {
      id: 1,
      title: 'Hoodies restocked',
      body: 'All sizes back this week.',
      audience: 'all',
      author: { id: 2, name: 'Ananya Rao' },
      publishedAt: new Date(Date.now() - 3 * 86_400_000).toISOString(),
      deliveries: { recipients: 46, queued: 0, sent: 46, failed: 0 },
    },
  ];
}

function loadAnnouncements(): StoredAnnouncement[] {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) return JSON.parse(raw) as StoredAnnouncement[];
  } catch {
    /* storage unavailable or corrupt */
  }
  const seeded = seedAnnouncements();
  saveAnnouncements(seeded);
  return seeded;
}

function saveAnnouncements(items: StoredAnnouncement[]): void {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(items));
  } catch {
    /* storage unavailable */
  }
}

function loadLogs(): StoredDeliveryLog[] {
  try {
    const raw = localStorage.getItem(LOG_KEY);
    if (raw) return JSON.parse(raw) as StoredDeliveryLog[];
  } catch {
    /* storage unavailable or corrupt */
  }
  return [];
}

function saveLogs(logs: StoredDeliveryLog[]): void {
  try {
    localStorage.setItem(LOG_KEY, JSON.stringify(logs));
  } catch {
    /* storage unavailable */
  }
}

function isComposer(): boolean {
  const user = getCurrentMockUser();
  return !!user?.roles.some((r) => COMPOSER_ROLES.includes(r));
}

function withVisibility(a: StoredAnnouncement): Announcement {
  return { ...a, deliveries: isComposer() ? a.deliveries : null };
}

export const mockAnnouncementsApi = {
  async list(page = 1): Promise<Paginated<Announcement>> {
    await delay(300);
    const all = loadAnnouncements()
      .slice()
      .sort((a, b) => b.publishedAt.localeCompare(a.publishedAt))
      .map(withVisibility);
    const start = (page - 1) * PAGE_SIZE;
    const results = all.slice(start, start + PAGE_SIZE);
    return { count: all.length, next: start + PAGE_SIZE < all.length ? `?page=${page + 1}` : null, previous: page > 1 ? `?page=${page - 1}` : null, results };
  },

  async get(id: number): Promise<Announcement> {
    await delay(250);
    const found = loadAnnouncements().find((a) => a.id === id);
    if (!found) throw new ApiRequestError({ code: 'not_found', message: 'No such announcement.' });
    return withVisibility(found);
  },

  async create({ title, body, audience = 'all' }: AnnouncementDraft): Promise<Announcement> {
    await delay(500);
    const user = getCurrentMockUser();
    if (!user) throw new ApiRequestError({ code: 'not_authenticated', message: 'No active session.' });
    if (!isComposer()) throw new ApiRequestError({ code: 'permission_denied', message: 'You cannot post announcements.' });

    const errors: { field: string; code: string; message: string }[] = [];
    if (!title.trim()) errors.push({ field: 'title', code: 'blank', message: 'This field may not be blank.' });
    if (title.length > 200) errors.push({ field: 'title', code: 'max_length', message: 'Title must be 200 characters or fewer.' });
    if (!body.trim()) errors.push({ field: 'body', code: 'blank', message: 'This field may not be blank.' });
    if (errors.length > 0) {
      throw new ApiRequestError({ code: 'validation_error', message: errors[0].message, field: errors[0].field, errors });
    }

    const recipients = listAllUsers().filter((u) => (audience === 'members' ? u.membershipStatus === 'active' : true));

    // A deterministic ~1-in-3 "failed" rate so the composer's failed-deliveries
    // warning and the delivery log's failed rows are both demonstrable even
    // against the handful of seed accounts, without being random/flaky.
    const entries: DeliveryLogEntry[] = recipients.map((recipient, i) => {
      const failed = recipients.length > 0 && i % 3 === 2;
      return {
        id: i + 1,
        recipient: { id: recipient.id, name: recipient.name, email: recipient.email },
        status: failed ? 'failed' : 'sent',
        attempts: failed ? 3 : 1,
        lastError: failed ? 'SMTP timeout' : null,
        updatedAt: new Date().toISOString(),
      };
    });
    const summary: DeliverySummary = {
      recipients: recipients.length,
      queued: 0,
      sent: entries.filter((e) => e.status === 'sent').length,
      failed: entries.filter((e) => e.status === 'failed').length,
    };

    const announcements = loadAnnouncements();
    const announcement: StoredAnnouncement = {
      id: announcements.reduce((max, a) => Math.max(max, a.id), 0) + 1,
      title: title.trim(),
      body,
      audience,
      author: { id: user.id, name: user.name },
      publishedAt: new Date().toISOString(),
      deliveries: summary,
    };
    announcements.push(announcement);
    saveAnnouncements(announcements);

    const logs = loadLogs();
    logs.push({ announcementId: announcement.id, entries });
    saveLogs(logs);

    return withVisibility(announcement);
  },

  async listDeliveries(id: number, page = 1): Promise<Paginated<DeliveryLogEntry>> {
    await delay(300);
    if (!isComposer()) throw new ApiRequestError({ code: 'permission_denied', message: 'You cannot view delivery logs.' });
    const log = loadLogs().find((l) => l.announcementId === id);
    const all = log?.entries ?? [];
    const start = (page - 1) * PAGE_SIZE;
    const results = all.slice(start, start + PAGE_SIZE);
    return { count: all.length, next: start + PAGE_SIZE < all.length ? `?page=${page + 1}` : null, previous: page > 1 ? `?page=${page - 1}` : null, results };
  },
};
