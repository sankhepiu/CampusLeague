import { ApiRequestError } from '../../api/client';
import { getCurrentMockUser } from '../auth/mockUsers';
import type { EventDraft, EventItem, EventStatus, Tier, TierDraft } from './types';

/** Internal mock record — capacity/price bookkeeping the public EventItem
 * doesn't carry (seatsLeft/price are derived per-caller at read time). */
interface MockTier {
  id: number;
  name: string;
  publicPrice: number;
  memberPrice: number;
  capacity: number;
  soldCount: number;
  saleOpens: string | null;
  saleCloses: string | null;
}

interface MockEvent {
  id: number;
  title: string;
  description: string;
  venue: string;
  startsAt: string;
  endsAt: string;
  capacityTotal: number;
  status: EventStatus;
  budgetAmount: number;
  tiers: MockTier[];
}

const STORE_KEY = 'campusleague.mock.events';
const inAMonth = (days: number) => new Date(Date.now() + days * 86_400_000).toISOString();

function seed(): MockEvent[] {
  return [
    {
      id: 1,
      title: 'Freshers Night',
      description: 'Welcome the newest members with games, music and snacks.',
      venue: 'Main Hall',
      startsAt: inAMonth(-10),
      endsAt: inAMonth(-10),
      capacityTotal: 60,
      status: 'closed',
      budgetAmount: 1_200_000,
      tiers: [{ id: 1, name: 'General', publicPrice: 15000, memberPrice: 10000, capacity: 60, soldCount: 35, saleOpens: null, saleCloses: null }],
    },
    {
      id: 2,
      title: 'Spring Gala',
      description: 'An evening of dinner, awards and dancing to close out the year.',
      venue: 'Grand Ballroom',
      startsAt: inAMonth(21),
      endsAt: inAMonth(21),
      capacityTotal: 120,
      status: 'on_sale',
      budgetAmount: 2_000_000,
      tiers: [
        { id: 2, name: 'Early Bird', publicPrice: 80000, memberPrice: 60000, capacity: 2, soldCount: 1, saleOpens: null, saleCloses: inAMonth(7) },
        { id: 3, name: 'General', publicPrice: 100000, memberPrice: 75000, capacity: 100, soldCount: 12, saleOpens: null, saleCloses: null },
        { id: 4, name: 'VIP', publicPrice: 150000, memberPrice: 120000, capacity: 0, soldCount: 0, saleOpens: null, saleCloses: null },
      ],
    },
    {
      id: 3,
      title: 'Hack Night (sale not open yet)',
      description: 'An overnight build session with prizes for the best projects.',
      venue: 'Lab 204',
      startsAt: inAMonth(45),
      endsAt: inAMonth(45),
      capacityTotal: 40,
      status: 'on_sale',
      budgetAmount: 400_000,
      tiers: [{ id: 5, name: 'General', publicPrice: 20000, memberPrice: 15000, capacity: 40, soldCount: 0, saleOpens: inAMonth(30), saleCloses: null }],
    },
  ];
}

function loadStore(): MockEvent[] {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) return JSON.parse(raw) as MockEvent[];
  } catch {
    /* storage unavailable or corrupt */
  }
  const seeded = seed();
  saveStore(seeded);
  return seeded;
}

function saveStore(events: MockEvent[]): void {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(events));
  } catch {
    /* storage unavailable */
  }
}

export function priceForCurrentUser(tier: MockTier): number {
  const user = getCurrentMockUser();
  return user?.membershipStatus === 'active' ? tier.memberPrice : tier.publicPrice;
}

function toPublicTier(tier: MockTier): Tier {
  return {
    id: tier.id,
    name: tier.name,
    publicPrice: tier.publicPrice,
    memberPrice: tier.memberPrice,
    price: priceForCurrentUser(tier),
    capacity: tier.capacity,
    seatsLeft: Math.max(0, tier.capacity - tier.soldCount),
    saleOpens: tier.saleOpens,
    saleCloses: tier.saleCloses,
  };
}

export function toPublicEvent(event: MockEvent): EventItem {
  return {
    id: event.id,
    title: event.title,
    description: event.description,
    venue: event.venue,
    startsAt: event.startsAt,
    endsAt: event.endsAt,
    capacityTotal: event.capacityTotal,
    status: event.status,
    tiers: event.tiers.map(toPublicTier),
  };
}

export function listMockEvents(): MockEvent[] {
  return loadStore();
}

export function getMockEvent(id: number): MockEvent | undefined {
  return loadStore().find((e) => e.id === id);
}

export function getMockTier(eventId: number, tierId: number): { event: MockEvent; tier: MockTier } | undefined {
  const event = getMockEvent(eventId);
  const tier = event?.tiers.find((t) => t.id === tierId);
  return event && tier ? { event, tier } : undefined;
}

function nextId(items: { id: number }[]): number {
  return items.reduce((max, i) => Math.max(max, i.id), 0) + 1;
}

export function createMockEvent(draft: EventDraft): MockEvent {
  if (draft.endsAt <= draft.startsAt) {
    throw new ApiRequestError({ code: 'validation_error', message: 'Event must end after it starts.', field: 'ends_at', errors: [{ field: 'ends_at', code: 'ends_before_start', message: 'Event must end after it starts.' }] });
  }
  const events = loadStore();
  const event: MockEvent = {
    id: nextId(events),
    title: draft.title,
    venue: draft.venue,
    startsAt: draft.startsAt,
    endsAt: draft.endsAt,
    capacityTotal: draft.capacityTotal,
    description: draft.description ?? '',
    status: draft.status ?? 'draft',
    budgetAmount: draft.budgetAmount ?? 0,
    tiers: [],
  };
  events.push(event);
  saveStore(events);
  return event;
}

export function updateMockEvent(id: number, patch: Partial<EventDraft>): MockEvent {
  const events = loadStore();
  const event = events.find((e) => e.id === id);
  if (!event) throw new ApiRequestError({ code: 'not_found', message: 'No such event.' });

  const nextStart = patch.startsAt ?? event.startsAt;
  const nextEnd = patch.endsAt ?? event.endsAt;
  if (nextEnd <= nextStart) {
    throw new ApiRequestError({ code: 'validation_error', message: 'Event must end after it starts.', field: 'ends_at', errors: [{ field: 'ends_at', code: 'ends_before_start', message: 'Event must end after it starts.' }] });
  }
  if (patch.capacityTotal !== undefined) {
    const tierCapacitySum = event.tiers.reduce((sum, t) => sum + t.capacity, 0);
    if (patch.capacityTotal < tierCapacitySum) {
      throw new ApiRequestError({
        code: 'validation_error',
        message: `Capacity can't be lower than the ${tierCapacitySum} seats already assigned to tiers.`,
        field: 'capacity_total',
        errors: [{ field: 'capacity_total', code: 'below_tier_capacity', message: 'Capacity is below the tiers’ total.' }],
      });
    }
  }

  Object.assign(event, {
    title: patch.title ?? event.title,
    venue: patch.venue ?? event.venue,
    startsAt: nextStart,
    endsAt: nextEnd,
    capacityTotal: patch.capacityTotal ?? event.capacityTotal,
    description: patch.description ?? event.description,
    status: patch.status ?? event.status,
    budgetAmount: patch.budgetAmount ?? event.budgetAmount,
  });
  saveStore(events);
  return event;
}

export function addMockTier(eventId: number, draft: TierDraft): MockTier {
  const events = loadStore();
  const event = events.find((e) => e.id === eventId);
  if (!event) throw new ApiRequestError({ code: 'not_found', message: 'No such event.' });

  if (event.tiers.some((t) => t.name.toLowerCase() === draft.name.toLowerCase())) {
    throw new ApiRequestError({
      code: 'validation_error',
      message: 'A tier with this name already exists on this event.',
      field: 'name',
      errors: [{ field: 'name', code: 'tier_name_taken', message: 'A tier with this name already exists.' }],
    });
  }
  const usedCapacity = event.tiers.reduce((sum, t) => sum + t.capacity, 0);
  if (usedCapacity + draft.capacity > event.capacityTotal) {
    throw new ApiRequestError({
      code: 'validation_error',
      message: `Only ${event.capacityTotal - usedCapacity} seats are left to assign.`,
      field: 'capacity',
      errors: [{ field: 'capacity', code: 'exceeds_event_capacity', message: 'Exceeds the event’s remaining capacity.' }],
    });
  }

  const tier: MockTier = {
    id: nextId(events.flatMap((e) => e.tiers)),
    name: draft.name,
    publicPrice: draft.publicPrice,
    memberPrice: draft.memberPrice,
    capacity: draft.capacity,
    soldCount: 0,
    saleOpens: draft.saleOpens ?? null,
    saleCloses: draft.saleCloses ?? null,
  };
  event.tiers.push(tier);
  saveStore(events);
  return tier;
}

/** Synchronous read-check-write with no `await` in between, to keep the race
 * window as small as possible within a single tab. True concurrent-purchase
 * correctness (two browsers racing for the last seat) is a server-side
 * row-lock guarantee the contract describes — this mock can't replicate it
 * faithfully and that scenario needs the real backend to verify. */
export function reserveMockSeats(eventId: number, tierId: number, quantity: number): void {
  const events = loadStore();
  const event = events.find((e) => e.id === eventId)!;
  const tier = event.tiers.find((t) => t.id === tierId)!;
  tier.soldCount += quantity;
  saveStore(events);
}

export function saveMockEvents(events: MockEvent[]): void {
  saveStore(events);
}

export type { MockEvent, MockTier };
