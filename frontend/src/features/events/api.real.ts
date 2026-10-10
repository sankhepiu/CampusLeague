import { request, type Paginated } from '../../api/client';
import type {
  Attendance,
  AttendanceTierRow,
  EventDraft,
  EventItem,
  EventStatus,
  Pnl,
  PnlAccountLine,
  Tier,
  TierDraft,
} from './types';

interface WireTier {
  id: number;
  name: string;
  public_price: number;
  member_price: number;
  price: number;
  capacity: number;
  seats_left: number;
  sale_opens: string | null;
  sale_closes: string | null;
}

interface WireEvent {
  id: number;
  title: string;
  description: string;
  venue: string;
  starts_at: string;
  ends_at: string;
  capacity_total: number;
  status: EventStatus;
  tiers: WireTier[];
}

interface WireAttendanceTier {
  id: number;
  name: string;
  capacity: number;
  sold: number;
  checked_in: number;
  no_shows: number;
}

interface WireAttendance {
  event: { id: number; title: string; status: EventStatus };
  capacity_total: number;
  sold: number;
  checked_in: number;
  no_shows: number;
  attendance_rate_pct: number | null;
  tiers: WireAttendanceTier[];
}

interface WirePnlAccountLine {
  code: string;
  name: string;
  amount: number;
}

interface WirePnl {
  event: { id: number; title: string; status: EventStatus };
  revenue: { total: number; by_account: WirePnlAccountLine[] };
  expenses: { total: number; by_account: WirePnlAccountLine[] };
  profit: number;
  budget: { amount: number; spent: number; remaining: number };
  attendance: { sold: number; checked_in: number; attendance_rate_pct: number | null };
}

function fromWireTier(t: WireTier): Tier {
  return {
    id: t.id,
    name: t.name,
    publicPrice: t.public_price,
    memberPrice: t.member_price,
    price: t.price,
    capacity: t.capacity,
    seatsLeft: t.seats_left,
    saleOpens: t.sale_opens,
    saleCloses: t.sale_closes,
  };
}

function fromWireEvent(e: WireEvent): EventItem {
  return {
    id: e.id,
    title: e.title,
    description: e.description,
    venue: e.venue,
    startsAt: e.starts_at,
    endsAt: e.ends_at,
    capacityTotal: e.capacity_total,
    status: e.status,
    tiers: e.tiers.map(fromWireTier),
  };
}

function fromWireAccountLine(l: WirePnlAccountLine): PnlAccountLine {
  return { code: l.code, name: l.name, amount: l.amount };
}

function fromWireAttendanceTier(t: WireAttendanceTier): AttendanceTierRow {
  return { id: t.id, name: t.name, capacity: t.capacity, sold: t.sold, checkedIn: t.checked_in, noShows: t.no_shows };
}

export const realEventsApi = {
  async list(page = 1): Promise<Paginated<EventItem>> {
    const result = await request<Paginated<WireEvent>>('/events', { query: { page } });
    return { ...result, results: result.results.map(fromWireEvent) };
  },

  async get(id: number): Promise<EventItem> {
    return fromWireEvent(await request<WireEvent>(`/events/${id}`));
  },

  async create(draft: EventDraft): Promise<EventItem> {
    const body = {
      title: draft.title,
      venue: draft.venue,
      starts_at: draft.startsAt,
      ends_at: draft.endsAt,
      capacity_total: draft.capacityTotal,
      ...(draft.description !== undefined ? { description: draft.description } : {}),
      ...(draft.status !== undefined ? { status: draft.status } : {}),
      ...(draft.budgetAmount !== undefined ? { budget_amount: draft.budgetAmount } : {}),
    };
    return fromWireEvent(await request<WireEvent>('/events', { method: 'POST', body }));
  },

  async update(id: number, draft: Partial<EventDraft>): Promise<EventItem> {
    const body: Record<string, unknown> = {};
    if (draft.title !== undefined) body.title = draft.title;
    if (draft.venue !== undefined) body.venue = draft.venue;
    if (draft.startsAt !== undefined) body.starts_at = draft.startsAt;
    if (draft.endsAt !== undefined) body.ends_at = draft.endsAt;
    if (draft.capacityTotal !== undefined) body.capacity_total = draft.capacityTotal;
    if (draft.description !== undefined) body.description = draft.description;
    if (draft.status !== undefined) body.status = draft.status;
    if (draft.budgetAmount !== undefined) body.budget_amount = draft.budgetAmount;
    return fromWireEvent(await request<WireEvent>(`/events/${id}`, { method: 'PATCH', body }));
  },

  async addTier(eventId: number, draft: TierDraft): Promise<Tier> {
    const body = {
      name: draft.name,
      public_price: draft.publicPrice,
      member_price: draft.memberPrice,
      capacity: draft.capacity,
      ...(draft.saleOpens !== undefined ? { sale_opens: draft.saleOpens } : {}),
      ...(draft.saleCloses !== undefined ? { sale_closes: draft.saleCloses } : {}),
    };
    return fromWireTier(await request<WireTier>(`/events/${eventId}/tiers`, { method: 'POST', body }));
  },

  async attendance(eventId: number): Promise<Attendance> {
    const a = await request<WireAttendance>(`/events/${eventId}/attendance`);
    return {
      event: a.event,
      capacityTotal: a.capacity_total,
      sold: a.sold,
      checkedIn: a.checked_in,
      noShows: a.no_shows,
      attendanceRatePct: a.attendance_rate_pct,
      tiers: a.tiers.map(fromWireAttendanceTier),
    };
  },

  async pnl(eventId: number): Promise<Pnl> {
    const p = await request<WirePnl>(`/events/${eventId}/pnl`);
    return {
      event: p.event,
      revenue: { total: p.revenue.total, byAccount: p.revenue.by_account.map(fromWireAccountLine) },
      expenses: { total: p.expenses.total, byAccount: p.expenses.by_account.map(fromWireAccountLine) },
      profit: p.profit,
      budget: p.budget,
      attendance: {
        sold: p.attendance.sold,
        checkedIn: p.attendance.checked_in,
        attendanceRatePct: p.attendance.attendance_rate_pct,
      },
    };
  },
};
