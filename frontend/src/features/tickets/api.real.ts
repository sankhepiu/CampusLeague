import { request, requestWithStatus, type Paginated } from '../../api/client';
import type { Pass, PassDetail, PurchaseTicketsRequest, PurchaseTicketsResult, Ticket, TicketOrder, TicketPayment } from './types';
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
  coupon: string | null;
  coupon_discount: number;
  total: number;
  payment_ref: string;
  needs_refund: boolean;
  created_at: string;
}

interface WirePayment {
  id: number;
  amount: number;
  status: TicketPayment['status'];
  gateway_ref: string;
  created_at: string;
}

export interface WirePass {
  pass_id: number;
  event: { id: number; title: string; starts_at: string; venue: string };
  tier: { id: number; name: string };
  quantity: number;
  admitted: number;
  remaining: number;
  qr_token: string;
  tickets: { id: number; code: string; status: Ticket['status'] }[];
  created_at: string;
}

export interface WirePassDetail extends WirePass {
  order: number;
  holder: { name: string };
  history: { at: string; by: string; count: number }[];
}

export function fromWirePass(p: WirePass): Pass {
  return {
    passId: p.pass_id,
    event: { id: p.event.id, title: p.event.title, startsAt: p.event.starts_at, venue: p.event.venue },
    tier: { id: p.tier.id, name: p.tier.name },
    quantity: p.quantity,
    admitted: p.admitted,
    remaining: p.remaining,
    qrToken: p.qr_token,
    tickets: p.tickets.map((t) => ({ id: t.id, code: t.code, status: t.status })),
    createdAt: p.created_at,
  };
}

function fromWirePassDetail(p: WirePassDetail): PassDetail {
  return { ...fromWirePass(p), order: p.order, holder: p.holder, history: p.history };
}

interface WirePurchaseResult {
  order: WireOrder;
  payment: WirePayment | null;
  tickets: WireTicket[];
  pass: WirePass | null;
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
  return {
    id: o.id,
    status: o.status,
    subtotal: o.subtotal,
    discount: o.discount,
    coupon: o.coupon,
    couponDiscount: o.coupon_discount,
    total: o.total,
    paymentRef: o.payment_ref,
    needsRefund: o.needs_refund,
    createdAt: o.created_at,
  };
}

function fromWirePayment(p: WirePayment): TicketPayment {
  return { id: p.id, amount: p.amount, status: p.status, gatewayRef: p.gateway_ref, createdAt: p.created_at };
}

export const realTicketsApi = {
  async purchase(eventId: number, { tier, quantity, testOutcome, coupon }: PurchaseTicketsRequest, idempotencyKey: string): Promise<PurchaseTicketsResult> {
    const { status, data: result } = await requestWithStatus<WirePurchaseResult>(`/events/${eventId}/tickets`, {
      method: 'POST',
      body: {
        tier,
        ...(quantity !== undefined ? { quantity } : {}),
        ...(testOutcome ? { test_outcome: testOutcome } : {}),
        ...(coupon ? { coupon } : {}),
      },
      headers: { 'Idempotency-Key': idempotencyKey },
    });
    return {
      order: fromWireOrder(result.order),
      payment: result.payment ? fromWirePayment(result.payment) : null,
      tickets: result.tickets.map(fromWireTicket),
      pass: result.pass ? fromWirePass(result.pass) : null,
      replayed: status === 200,
    };
  },

  /** Breaking change in the contract: this now returns passes, not
   * individual tickets — each pass groups every ticket from one purchase
   * under a single QR. */
  async listMine(page = 1): Promise<Paginated<Pass>> {
    const result = await request<Paginated<WirePass>>('/tickets/me', { query: { page } });
    return { ...result, results: result.results.map(fromWirePass) };
  },

  async getPass(id: number): Promise<PassDetail> {
    return fromWirePassDetail(await request<WirePassDetail>(`/tickets/passes/${id}`));
  },

  // GAP: not yet in docs/API_CONTRACT.md — see the matching comment in
  // features/membership/api.real.ts for the shape this was built against.
  async createRazorpayOrder(eventId: number, tier: number, quantity: number, idempotencyKey: string, coupon?: string): Promise<RazorpayOrderInfo> {
    return fromWireRazorpayOrderInfo(
      await request<WireRazorpayOrderInfo>('/payments/razorpay/order', {
        method: 'POST',
        // The coupon has to go with the order: Razorpay charges what the
        // server prices here, so leaving it out charges the full price.
        body: { purpose: 'tickets', event: eventId, tier, quantity, ...(coupon ? { coupon } : {}) },
        headers: { 'Idempotency-Key': idempotencyKey },
      }),
    );
  },

  async verifyRazorpayPayment(orderId: number, fields: RazorpayVerifyFields): Promise<PurchaseTicketsResult> {
    const { status, data: result } = await requestWithStatus<WirePurchaseResult>('/payments/razorpay/verify', {
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
      pass: result.pass ? fromWirePass(result.pass) : null,
      // The contract says a repeat verify of the same payment returns 200
      // with the same body and charges nothing — same replay semantics as
      // every other purchase endpoint.
      replayed: status === 200,
    };
  },

  async cancelRazorpayPayment(orderId: number): Promise<void> {
    await request('/payments/razorpay/cancel', { method: 'POST', body: { order_id: orderId } });
  },
};
