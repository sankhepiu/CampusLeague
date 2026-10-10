import { request, requestWithStatus, type Paginated } from '../../api/client';
import type { PurchaseTicketsRequest, PurchaseTicketsResult, Ticket, TicketOrder, TicketPayment } from './types';
import type { RazorpayOrderInfo, RazorpayVerifyFields } from '../payments/types';

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

interface WireRazorpayOrderInfo {
  order_id: number;
  razorpay_order_id: string;
  key: string;
  amount: number;
  currency: string;
  name: string;
  description: string;
  prefill: { name: string; email: string };
}

function fromWireRazorpayOrderInfo(r: WireRazorpayOrderInfo): RazorpayOrderInfo {
  return {
    orderId: r.order_id,
    razorpayOrderId: r.razorpay_order_id,
    key: r.key,
    amount: r.amount,
    currency: r.currency,
    name: r.name,
    description: r.description,
    prefill: r.prefill,
  };
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

  // GAP: not yet in docs/API_CONTRACT.md — see the matching comment in
  // features/membership/api.real.ts for the shape this was built against.
  async createRazorpayOrder(eventId: number, tier: number, quantity: number, idempotencyKey: string): Promise<RazorpayOrderInfo> {
    return fromWireRazorpayOrderInfo(
      await request<WireRazorpayOrderInfo>('/payments/razorpay/order', {
        method: 'POST',
        body: { purpose: 'tickets', event: eventId, tier, quantity },
        headers: { 'Idempotency-Key': idempotencyKey },
      }),
    );
  },

  async verifyRazorpayPayment(orderId: number, fields: RazorpayVerifyFields): Promise<PurchaseTicketsResult> {
    const result = await request<WirePurchaseResult>('/payments/razorpay/verify', {
      method: 'POST',
      body: {
        order_id: orderId,
        razorpay_order_id: fields.razorpayOrderId,
        razorpay_payment_id: fields.razorpayPaymentId,
        razorpay_signature: fields.razorpaySignature,
      },
    });
    return {
      order: fromWireOrder(result.order),
      payment: result.payment ? fromWirePayment(result.payment) : null,
      tickets: result.tickets.map(fromWireTicket),
      replayed: false,
    };
  },

  async cancelRazorpayPayment(orderId: number): Promise<void> {
    await request('/payments/razorpay/cancel', { method: 'POST', body: { order_id: orderId } });
  },
};
