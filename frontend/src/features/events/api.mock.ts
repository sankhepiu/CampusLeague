import { ApiRequestError, type Paginated } from '../../api/client';
import { countsForMockEvent, revenueForMockEvent } from '../tickets/mockTicketsStore';
import {
  addMockTier,
  createMockEvent,
  getMockEvent,
  listMockEvents,
  toPublicEvent,
  updateMockEvent,
} from './mockEventsStore';
import type { Attendance, EventDraft, EventItem, Pnl, Tier, TierDraft } from './types';

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const PAGE_SIZE = 20;

function paginate<T>(items: T[], page: number): Paginated<T> {
  const start = (page - 1) * PAGE_SIZE;
  const results = items.slice(start, start + PAGE_SIZE);
  return {
    count: items.length,
    next: start + PAGE_SIZE < items.length ? `?page=${page + 1}` : null,
    previous: page > 1 ? `?page=${page - 1}` : null,
    results,
  };
}

export const mockEventsApi = {
  async list(page = 1): Promise<Paginated<EventItem>> {
    await delay(300);
    return paginate(listMockEvents().map(toPublicEvent), page);
  },

  async get(id: number): Promise<EventItem> {
    await delay(250);
    const event = getMockEvent(id);
    if (!event) throw new ApiRequestError({ code: 'not_found', message: 'No such event.' });
    return toPublicEvent(event);
  },

  async create(draft: EventDraft): Promise<EventItem> {
    await delay(400);
    return toPublicEvent(createMockEvent(draft));
  },

  async update(id: number, draft: Partial<EventDraft>): Promise<EventItem> {
    await delay(400);
    return toPublicEvent(updateMockEvent(id, draft));
  },

  async addTier(eventId: number, draft: TierDraft): Promise<Tier> {
    await delay(400);
    addMockTier(eventId, draft);
    const event = getMockEvent(eventId)!;
    return toPublicEvent(event).tiers.find((t) => t.name === draft.name)!;
  },

  async attendance(eventId: number): Promise<Attendance> {
    await delay(300);
    const event = getMockEvent(eventId);
    if (!event) throw new ApiRequestError({ code: 'not_found', message: 'No such event.' });
    const counts = countsForMockEvent(eventId);
    const isOver = new Date(event.endsAt) < new Date();
    return {
      event: { id: event.id, title: event.title, status: event.status },
      capacityTotal: event.capacityTotal,
      sold: counts.sold,
      checkedIn: counts.checkedIn,
      noShows: isOver ? counts.noShows : 0,
      attendanceRatePct: counts.sold === 0 ? null : Math.round((counts.checkedIn / counts.sold) * 1000) / 10,
      tiers: event.tiers.map((t) => {
        const row = counts.byTier.get(t.id) ?? { id: t.id, sold: 0, checkedIn: 0 };
        return { id: t.id, name: t.name, capacity: t.capacity, sold: row.sold, checkedIn: row.checkedIn, noShows: isOver ? row.sold - row.checkedIn : 0 };
      }),
    };
  },

  async pnl(eventId: number): Promise<Pnl> {
    await delay(300);
    const event = getMockEvent(eventId);
    if (!event) throw new ApiRequestError({ code: 'not_found', message: 'No such event.' });
    const counts = countsForMockEvent(eventId);
    const revenueTotal = revenueForMockEvent(eventId);
    const spent = 0; // expenses (Phase 4 reimbursements) aren't posted yet, matching the contract note
    return {
      event: { id: event.id, title: event.title, status: event.status },
      revenue: { total: revenueTotal, byAccount: revenueTotal > 0 ? [{ code: '4100', name: 'Ticket revenue', amount: revenueTotal }] : [] },
      expenses: { total: 0, byAccount: [] },
      profit: revenueTotal - spent,
      budget: { amount: event.budgetAmount, spent, remaining: event.budgetAmount - spent },
      attendance: {
        sold: counts.sold,
        checkedIn: counts.checkedIn,
        attendanceRatePct: counts.sold === 0 ? null : Math.round((counts.checkedIn / counts.sold) * 1000) / 10,
      },
    };
  },
};
