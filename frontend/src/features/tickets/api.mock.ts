import { ApiRequestError, type Paginated } from '../../api/client';
import { getCurrentMockUser } from '../auth/mockUsers';
import { getMockTier, priceForCurrentUser, reserveMockSeats } from '../events/mockEventsStore';
import { createMockTickets, listMockTicketsForUser, toPublicTicket } from './mockTicketsStore';
import type { PurchaseTicketsRequest, PurchaseTicketsResult, Ticket, TicketOrder, TicketPayment } from './types';

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const PAGE_SIZE = 20;

interface IdempotencyRecord {
  userEmail: string;
  eventId: number;
  tier: number;
  quantity: number;
  result: PurchaseTicketsResult;
}

const IDEMPOTENCY_KEY = 'campusleague.mock.ticketIdempotency';

function loadIdempotency(): Record<string, IdempotencyRecord> {
  try {
    const raw = localStorage.getItem(IDEMPOTENCY_KEY);
    if (raw) return JSON.parse(raw) as Record<string, IdempotencyRecord>;
  } catch {
    /* storage unavailable or corrupt */
  }
  return {};
}

function saveIdempotency(store: Record<string, IdempotencyRecord>): void {
  try {
    localStorage.setItem(IDEMPOTENCY_KEY, JSON.stringify(store));
  } catch {
    /* storage unavailable */
  }
}

function isSaleOpen(event: { status: string }, tier: { saleOpens: string | null; saleCloses: string | null }): boolean {
  if (event.status !== 'on_sale') return false;
  const now = Date.now();
  if (tier.saleOpens && now < new Date(tier.saleOpens).getTime()) return false;
  if (tier.saleCloses && now > new Date(tier.saleCloses).getTime()) return false;
  return true;
}

const mockGatewayRef = () => `mock_${Date.now().toString(16)}${Math.random().toString(16).slice(2, 10)}`;

export const mockTicketsApi = {
  async purchase(eventId: number, { tier: tierId, quantity = 1, testOutcome = 'success' }: PurchaseTicketsRequest, idempotencyKey: string): Promise<PurchaseTicketsResult> {
    await delay(700);
    const user = getCurrentMockUser();
    if (!user) throw new ApiRequestError({ code: 'not_authenticated', message: 'No active session.' });

    if (quantity < 1 || quantity > 10) {
      throw new ApiRequestError({ code: 'validation_error', message: 'Quantity must be between 1 and 10.', field: 'quantity' });
    }

    const idempotency = loadIdempotency();
    const replay = idempotency[idempotencyKey];
    if (replay) {
      if (replay.userEmail !== user.email || replay.eventId !== eventId || replay.tier !== tierId) {
        throw new ApiRequestError({ code: 'idempotency_key_reused', message: 'This idempotency key already paid for a different purchase.' });
      }
      return replay.result;
    }

    const found = getMockTier(eventId, tierId);
    if (!found) {
      throw new ApiRequestError({ code: 'validation_error', message: 'That tier is not part of this event.', field: 'tier' });
    }
    const { event, tier } = found;

    if (!isSaleOpen(event, tier)) {
      throw new ApiRequestError({ code: 'sales_closed', message: 'Tickets are not on sale for this tier right now.' });
    }

    const seatsLeft = tier.capacity - tier.soldCount;
    if (quantity > seatsLeft) {
      throw new ApiRequestError({ code: 'sold_out', message: `Only ${seatsLeft} seat${seatsLeft === 1 ? '' : 's'} left in ${tier.name}.` });
    }

    if (testOutcome === 'failure') {
      throw new ApiRequestError({ code: 'payment_failed', message: 'The mock payment gateway declined this attempt.' });
    }

    const orderId = Date.now() + Math.floor(Math.random() * 1000);
    const createdAt = new Date().toISOString();
    const unitPrice = priceForCurrentUser(tier);

    if (testOutcome === 'pending') {
      const order: TicketOrder = {
        id: orderId,
        status: 'pending',
        subtotal: unitPrice * quantity,
        discount: 0,
        total: unitPrice * quantity,
        paymentRef: '',
        createdAt,
      };
      // Pending attempts hold no seat and are never remembered against the
      // idempotency key, matching the contract.
      return { order, payment: null, tickets: [] };
    }

    reserveMockSeats(eventId, tierId, quantity);
    const tickets = createMockTickets({
      eventId,
      eventTitle: event.title,
      eventVenue: event.venue,
      eventStartsAt: event.startsAt,
      tierId,
      tierName: tier.name,
      ownerEmail: user.email,
      ownerName: user.name,
      unitPrice,
      quantity,
    });

    const gatewayRef = mockGatewayRef();
    const order: TicketOrder = {
      id: orderId,
      status: 'paid',
      subtotal: unitPrice * quantity,
      discount: 0,
      total: unitPrice * quantity,
      paymentRef: gatewayRef,
      createdAt,
    };
    const payment: TicketPayment = { id: orderId + 1, amount: unitPrice * quantity, status: 'succeeded', gatewayRef, createdAt };
    const result: PurchaseTicketsResult = { order, payment, tickets: tickets.map(toPublicTicket) };

    idempotency[idempotencyKey] = { userEmail: user.email, eventId, tier: tierId, quantity, result };
    saveIdempotency(idempotency);

    return result;
  },

  async listMine(page = 1): Promise<Paginated<Ticket>> {
    await delay(300);
    const user = getCurrentMockUser();
    if (!user) throw new ApiRequestError({ code: 'not_authenticated', message: 'No active session.' });
    const all = listMockTicketsForUser(user.email).map(toPublicTicket);
    const start = (page - 1) * PAGE_SIZE;
    const results = all.slice(start, start + PAGE_SIZE);
    return {
      count: all.length,
      next: start + PAGE_SIZE < all.length ? `?page=${page + 1}` : null,
      previous: page > 1 ? `?page=${page - 1}` : null,
      results,
    };
  },
};
