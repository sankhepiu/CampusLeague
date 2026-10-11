import type { MembershipStatus } from '../auth/types';
import type { Pass, PassDetail, Ticket, TicketStatus } from './types';

/** Internal mock record — richer than the public Ticket object, since
 * check-in needs to look tickets up by code/token and remember who scanned
 * them and when (for the "already checked in" replay). Shared by the
 * tickets mock (purchase, my-tickets), the events mock (attendance/P&L) and
 * the check-in mock. */
export interface MockTicketRecord {
  id: number;
  code: string;
  qrToken: string;
  status: TicketStatus;
  pricePaid: number;
  eventId: number;
  eventTitle: string;
  eventVenue: string;
  eventStartsAt: string;
  tierId: number;
  tierName: string;
  ownerEmail: string;
  ownerName: string;
  createdAt: string;
  checkedInAt?: string;
  checkedInBy?: string;
  membershipStatusAtCheckin?: MembershipStatus;
  /** Every ticket in one purchase shares a passId — the group pass that
   * admits all of them with one QR. Seeded tickets (bought before passes
   * existed, same as the real backend's migration note) get one pass each. */
  passId: number;
  orderId: number;
}

/** One line per scan that admitted at least one person on a pass — mirrors
 * the real contract's `history: [{ at, by, count }]` on a pass's detail. */
export interface MockPassScanLogEntry {
  passId: number;
  at: string;
  by: string;
  count: number;
}

const SCAN_LOG_KEY = 'campusleague.mock.passScanLog';

function loadScanLog(): MockPassScanLogEntry[] {
  try {
    const raw = localStorage.getItem(SCAN_LOG_KEY);
    if (raw) return JSON.parse(raw) as MockPassScanLogEntry[];
  } catch {
    /* storage unavailable or corrupt */
  }
  return [];
}

function saveScanLog(entries: MockPassScanLogEntry[]): void {
  try {
    localStorage.setItem(SCAN_LOG_KEY, JSON.stringify(entries));
  } catch {
    /* storage unavailable */
  }
}

export function recordPassScan(passId: number, by: string, count: number): void {
  const log = loadScanLog();
  log.push({ passId, at: new Date().toISOString(), by, count });
  saveScanLog(log);
}

export function passScanHistory(passId: number): MockPassScanLogEntry[] {
  return loadScanLog()
    .filter((e) => e.passId === passId)
    .sort((a, b) => a.at.localeCompare(b.at));
}

const STORE_KEY = 'campusleague.mock.tickets';
const CODE_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; // no 0/O/1/I, easier to read aloud

function randomCode(): string {
  let code = '';
  for (let i = 0; i < 8; i++) code += CODE_CHARS[Math.floor(Math.random() * CODE_CHARS.length)];
  return code;
}

/** Backs Freshers Night's seeded 35 sold / 30 checked-in (matching the
 * contract's own attendance example exactly) and Spring Gala's early sales,
 * so Attendance/P&L always agrees with the tiers' seeded `soldCount` instead
 * of reporting zero until a real purchase happens in the session. */
function seedTickets(): MockTicketRecord[] {
  const tickets: MockTicketRecord[] = [];
  let id = 1;
  // Seeded tickets predate passes, so each gets its own one-ticket pass —
  // the same rule the real backend's migration applied.
  const push = (params: Omit<MockTicketRecord, 'id' | 'code' | 'qrToken' | 'createdAt' | 'passId' | 'orderId'>) => {
    tickets.push({
      ...params,
      id,
      code: randomCode(),
      qrToken: `mock-ticket:${id}:seed`,
      createdAt: params.checkedInAt ?? new Date().toISOString(),
      passId: id,
      orderId: id,
    });
    id++;
  };

  for (let i = 0; i < 35; i++) {
    push({
      eventId: 1,
      eventTitle: 'Freshers Night',
      eventVenue: 'Main Hall',
      eventStartsAt: new Date(Date.now() - 10 * 86_400_000).toISOString(),
      tierId: 1,
      tierName: 'General',
      ownerEmail: `seed.fresher${i}@campusleague.dev`,
      ownerName: `Seed Attendee ${i + 1}`,
      pricePaid: 10000,
      status: i < 30 ? 'checked_in' : 'valid',
      ...(i < 30 ? { checkedInAt: new Date(Date.now() - 10 * 86_400_000).toISOString(), checkedInBy: 'Dev', membershipStatusAtCheckin: 'active' as const } : {}),
    });
  }
  for (let i = 0; i < 1; i++) {
    push({ eventId: 2, eventTitle: 'Spring Gala', eventVenue: 'Grand Ballroom', eventStartsAt: new Date(Date.now() + 21 * 86_400_000).toISOString(), tierId: 2, tierName: 'Early Bird', ownerEmail: `seed.gala.eb${i}@campusleague.dev`, ownerName: `Seed Gala ${i + 1}`, pricePaid: 60000, status: 'valid' });
  }
  for (let i = 0; i < 12; i++) {
    push({ eventId: 2, eventTitle: 'Spring Gala', eventVenue: 'Grand Ballroom', eventStartsAt: new Date(Date.now() + 21 * 86_400_000).toISOString(), tierId: 3, tierName: 'General', ownerEmail: `seed.gala.gen${i}@campusleague.dev`, ownerName: `Seed Gala ${i + 1}`, pricePaid: 75000, status: 'valid' });
  }
  return tickets;
}

function loadStore(): MockTicketRecord[] {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) return JSON.parse(raw) as MockTicketRecord[];
  } catch {
    /* storage unavailable or corrupt */
  }
  const seeded = seedTickets();
  saveStore(seeded);
  return seeded;
}

function saveStore(tickets: MockTicketRecord[]): void {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(tickets));
  } catch {
    /* storage unavailable */
  }
}

export function toPublicTicket(t: MockTicketRecord): Ticket {
  return {
    id: t.id,
    code: t.code,
    qrToken: t.qrToken,
    status: t.status,
    pricePaid: t.pricePaid,
    event: { id: t.eventId, title: t.eventTitle, venue: t.eventVenue, startsAt: t.eventStartsAt },
    tier: { id: t.tierId, name: t.tierName },
    createdAt: t.createdAt,
  };
}

export function createMockTickets(
  params: {
    eventId: number;
    eventTitle: string;
    eventVenue: string;
    eventStartsAt: string;
    tierId: number;
    tierName: string;
    ownerEmail: string;
    ownerName: string;
    unitPrice: number;
    quantity: number;
    orderId: number;
  },
): MockTicketRecord[] {
  const store = loadStore();
  const baseId = store.reduce((max, t) => Math.max(max, t.id), 0);
  const createdAt = new Date().toISOString();
  // Every ticket from this one purchase shares a pass — the pass's own id
  // is the first ticket's id, same convention a real auto-increment DB would
  // give a 1:1 "pass row created alongside the first ticket" design.
  const passId = baseId + 1;
  const created: MockTicketRecord[] = Array.from({ length: params.quantity }, (_, i) => {
    const id = baseId + i + 1;
    return {
      id,
      code: randomCode(),
      qrToken: `mock-ticket:${id}:${Math.random().toString(16).slice(2)}`,
      status: 'valid',
      pricePaid: params.unitPrice,
      eventId: params.eventId,
      eventTitle: params.eventTitle,
      eventVenue: params.eventVenue,
      eventStartsAt: params.eventStartsAt,
      tierId: params.tierId,
      tierName: params.tierName,
      ownerEmail: params.ownerEmail,
      ownerName: params.ownerName,
      createdAt,
      passId,
      orderId: params.orderId,
    };
  });
  saveStore([...store, ...created]);
  return created;
}

export function listMockTicketsForUser(email: string): MockTicketRecord[] {
  return loadStore()
    .filter((t) => t.ownerEmail === email)
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

/** Every ticket across every owner — the finance ledger mock needs this to
 * derive ticket-sale entries, since seeded tickets never go through
 * POST /events/{id}/tickets and so never reach the shared orders store. */
export function listAllMockTickets(): MockTicketRecord[] {
  return loadStore();
}

function normalizeCode(code: string): string {
  return code.replace(/[\s-]/g, '').toUpperCase();
}

export function findMockTicketByCodeOrToken(params: { token?: string; code?: string }): MockTicketRecord | undefined {
  const store = loadStore();
  if (params.token) return store.find((t) => t.qrToken === params.token);
  if (params.code) {
    const normalized = normalizeCode(params.code);
    return store.find((t) => normalizeCode(t.code) === normalized);
  }
  return undefined;
}

export function saveMockTicket(updated: MockTicketRecord): void {
  const store = loadStore();
  const index = store.findIndex((t) => t.id === updated.id);
  if (index >= 0) store[index] = updated;
  saveStore(store);
}

function saveMockTickets(updated: MockTicketRecord[]): void {
  const store = loadStore();
  for (const u of updated) {
    const index = store.findIndex((t) => t.id === u.id);
    if (index >= 0) store[index] = u;
  }
  saveStore(store);
}

export function passQrToken(passId: number): string {
  return `mock-pass:${passId}`;
}

export function getMockPassTickets(passId: number): MockTicketRecord[] {
  return loadStore()
    .filter((t) => t.passId === passId)
    .sort((a, b) => a.id - b.id);
}

export function toPublicPass(tickets: MockTicketRecord[]): Pass {
  const first = tickets[0];
  const notCancelled = tickets.filter((t) => t.status !== 'cancelled');
  return {
    passId: first.passId,
    event: { id: first.eventId, title: first.eventTitle, startsAt: first.eventStartsAt, venue: first.eventVenue },
    tier: { id: first.tierId, name: first.tierName },
    quantity: notCancelled.length,
    admitted: notCancelled.filter((t) => t.status === 'checked_in').length,
    remaining: notCancelled.filter((t) => t.status === 'valid').length,
    qrToken: passQrToken(first.passId),
    tickets: tickets.map((t) => ({ id: t.id, code: t.code, status: t.status })),
    createdAt: first.createdAt,
  };
}

export function toPublicPassDetail(tickets: MockTicketRecord[]): PassDetail {
  const first = tickets[0];
  return {
    ...toPublicPass(tickets),
    order: first.orderId,
    holder: { name: first.ownerName },
    history: passScanHistory(first.passId).map((e) => ({ at: e.at, by: e.by, count: e.count })),
  };
}

/** Every distinct pass this user owns, newest first — groups the flat
 * ticket store by passId the same way `GET /tickets/me` groups tickets into
 * passes server-side. */
export function listMockPassesForUser(email: string): Pass[] {
  const byPass = new Map<number, MockTicketRecord[]>();
  for (const t of listMockTicketsForUser(email)) {
    const group = byPass.get(t.passId) ?? [];
    group.push(t);
    byPass.set(t.passId, group);
  }
  return Array.from(byPass.values())
    .map(toPublicPass)
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

/** This user's own passes for one event — backs the event overview's
 * `my_passes` field. */
export function listMockPassesForUserAndEvent(email: string, eventId: number): Pass[] {
  return listMockPassesForUser(email).filter((p) => p.event.id === eventId);
}

export function findMockPassTicketsByToken(token: string): MockTicketRecord[] | undefined {
  const match = /^mock-pass:(\d+)$/.exec(token);
  if (!match) return undefined;
  const tickets = getMockPassTickets(Number(match[1]));
  return tickets.length > 0 ? tickets : undefined;
}

/** Admits up to `count` of this pass's still-valid tickets, recording one
 * scan-log line for the group (so history shows one entry per scan, not one
 * per ticket). Returns the tickets actually admitted by this call. */
export function admitMockPass(passId: number, count: number, by: string, membershipStatusAtCheckin: MembershipStatus): MockTicketRecord[] {
  const tickets = getMockPassTickets(passId);
  const checkedInAt = new Date().toISOString();
  const toAdmit = tickets.filter((t) => t.status === 'valid').slice(0, count);
  const updated = toAdmit.map((t) => ({ ...t, status: 'checked_in' as const, checkedInAt, checkedInBy: by, membershipStatusAtCheckin }));
  saveMockTickets(updated);
  if (updated.length > 0) recordPassScan(passId, by, updated.length);
  return updated;
}

/** Sum of what was actually paid for this event's non-cancelled tickets —
 * mirrors how the real ledger sums posted lines rather than re-deriving
 * revenue from today's tier prices. */
export function revenueForMockEvent(eventId: number): number {
  return loadStore()
    .filter((t) => t.eventId === eventId && t.status !== 'cancelled')
    .reduce((sum, t) => sum + t.pricePaid, 0);
}

export function countsForMockEvent(eventId: number) {
  const tickets = loadStore().filter((t) => t.eventId === eventId);
  const sold = tickets.filter((t) => t.status !== 'cancelled').length;
  const checkedIn = tickets.filter((t) => t.status === 'checked_in').length;
  const byTier = new Map<number, { id: number; sold: number; checkedIn: number }>();
  for (const t of tickets) {
    if (t.status === 'cancelled') continue;
    const row = byTier.get(t.tierId) ?? { id: t.tierId, sold: 0, checkedIn: 0 };
    row.sold += 1;
    if (t.status === 'checked_in') row.checkedIn += 1;
    byTier.set(t.tierId, row);
  }
  return { sold, checkedIn, noShows: sold - checkedIn, byTier };
}
