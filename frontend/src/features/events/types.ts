import type { Pass } from '../tickets/types';

export type EventStatus = 'draft' | 'on_sale' | 'closed';

export interface Tier {
  id: number;
  name: string;
  publicPrice: number; // paise
  memberPrice: number; // paise
  price: number; // paise — what the caller pays now (server-decided)
  capacity: number;
  sold: number;
  seatsLeft: number;
  saleOpens: string | null;
  saleCloses: string | null;
  /** The event is on_sale and now is inside this tier's window — says
   * nothing about seats, a tier can be open and sold out at once. */
  saleOpen: boolean;
}

export interface EventSummary {
  id: number;
  title: string;
  status: EventStatus;
}

export interface EventItem {
  id: number;
  title: string;
  description: string;
  venue: string;
  startsAt: string;
  endsAt: string;
  capacityTotal: number;
  status: EventStatus;
  tiers: Tier[];
}

/** The extra fields `GET /events/{id}` adds on top of `EventItem` — not
 * present on the list endpoint. `revenue`/`attendancePct` are present only
 * for president/event manager, absent (not merely null) for everyone else. */
export interface EventDetail extends EventItem {
  organiser: { name: string };
  capacity: number;
  sold: number;
  seatsLeft: number;
  checkedIn: number;
  myPasses: Pass[];
  revenue?: number; // paise
  attendancePct?: number | null;
}

export interface EventDraft {
  title: string;
  venue: string;
  startsAt: string;
  endsAt: string;
  capacityTotal: number;
  description?: string;
  status?: EventStatus;
  /** Paise — never returned by the public endpoints, only usable by staff. */
  budgetAmount?: number;
}

export interface TierDraft {
  name: string;
  publicPrice: number;
  memberPrice: number;
  capacity: number;
  saleOpens?: string | null;
  saleCloses?: string | null;
}

export interface AttendanceTierRow {
  id: number;
  name: string;
  capacity: number;
  sold: number;
  checkedIn: number;
  noShows: number;
}

export interface Attendance {
  event: EventSummary;
  capacityTotal: number;
  sold: number;
  checkedIn: number;
  noShows: number;
  attendanceRatePct: number | null;
  tiers: AttendanceTierRow[];
}

export interface PnlAccountLine {
  code: string;
  name: string;
  amount: number; // paise
}

export interface Pnl {
  event: EventSummary;
  revenue: { total: number; byAccount: PnlAccountLine[] };
  expenses: { total: number; byAccount: PnlAccountLine[] };
  profit: number; // paise, can be negative
  budget: { amount: number; spent: number; remaining: number }; // paise
  attendance: { sold: number; checkedIn: number; attendanceRatePct: number | null };
}
