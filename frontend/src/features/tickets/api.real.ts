import { request, requestWithStatus, type Paginated } from '../../api/client';
import type { PurchaseTicketsRequest, PurchaseTicketsResult, Ticket, TicketOrder, TicketPayment } from './types';

interface WireTicket {
  id: number;
  code: string;
  qr_token: string;
  status: Ticket['status'];
  price_paid: number;
  event: { id: number; title: string; venue: string; starts_at: string };
  tier: { id: number; name: string };
  created_at: string;
}

interface WireOrder {
  id: number;
  status: TicketOrder['status'];
  subtotal: number;
  discount: number;
  total: number;
  payment_ref: string;
  created_at: string;
}

interface WirePayment {
  id: number;
  amount: number;
  status: TicketPayment['status'];
  gateway_ref: string;
  created_at: string;
}

interface WirePurchaseResult {
  order: WireOrder;
  payment: WirePayment | null;
  tickets: WireTicket[];
}

function fromWireTicket(t: WireTicket): Ticket {
  return {
    id: t.id,
    code: t.code,
    qrToken: t.qr_token,
    status: t.status,
    pricePaid: t.price_paid,
    event: { id: t.event.id, title: t.event.title, venue: t.event.venue, startsAt: t.event.starts_at },
    tier: { id: t.tier.id, name: t.tier.name },
    createdAt: t.created_at,
  };
}

function fromWireOrder(o: WireOrder): TicketOrder {
  return { id: o.id, status: o.status, subtotal: o.subtotal, discount: o.discount, total: o.total, paymentRef: o.payment_ref, createdAt: o.created_at };
}

function fromWirePayment(p: WirePayment): TicketPayment {
  return { id: p.id, amount: p.amount, status: p.status, gatewayRef: p.gateway_ref, createdAt: p.created_at };
}

export const realTicketsApi = {
  async purchase(eventId: number, { tier, quantity, testOutcome }: PurchaseTicketsRequest, idempotencyKey: string): Promise<PurchaseTicketsResult> {
    const { status, data: result } = await requestWithStatus<WirePurchaseResult>(`/events/${eventId}/tickets`, {
      method: 'POST',
      body: { tier, ...(quantity !== undefined ? { quantity } : {}), ...(testOutcome ? { test_outcome: testOutcome } : {}) },
      headers: { 'Idempotency-Key': idempotencyKey },
    });
    return {
      order: fromWireOrder(result.order),
      payment: result.payment ? fromWirePayment(result.payment) : null,
      tickets: result.tickets.map(fromWireTicket),
      replayed: status === 200,
    };
  },

  async listMine(page = 1): Promise<Paginated<Ticket>> {
    const result = await request<Paginated<WireTicket>>('/tickets/me', { query: { page } });
    return { ...result, results: result.results.map(fromWireTicket) };
  },
};
