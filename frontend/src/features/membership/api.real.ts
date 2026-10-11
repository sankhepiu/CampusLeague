import { request, requestWithStatus, type Paginated } from '../../api/client';
import type { MyMembership, Order, Payment, Plan, MembershipRecord, PurchaseRequest, PurchaseResult } from './types';
import type { RazorpayOrderInfo, RazorpayVerifyFields } from '../payments/types';

interface WirePlan {
  id: number;
  name: string;
  price: number;
  duration_months: number;
  ticket_discount_pct: number;
  merch_discount_pct: number;
}

interface WireMembership {
  id: number;
  plan: WirePlan;
  status: MembershipRecord['status'];
  start_date: string;
  end_date: string;
}

interface WireOrderLine {
  id: number;
  kind: string;
  plan: number;
  qty: number;
  unit_price: number;
}

interface WireOrder {
  id: number;
  status: Order['status'];
  subtotal: number;
  discount: number;
  total: number;
  payment_ref: string;
  created_at: string;
  lines: WireOrderLine[];
}

interface WirePayment {
  id: number;
  amount: number;
  status: Payment['status'];
  gateway_ref: string;
  created_at: string;
}

interface WirePurchaseResult {
  order: WireOrder;
  payment: WirePayment | null;
  membership: WireMembership | null;
}

interface WireMyMembership {
  status: MyMembership['status'];
  membership: WireMembership | null;
  paid_until: string | null;
  member_qr_token: string | null;
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

function fromWirePlan(p: WirePlan): Plan {
  return {
    id: p.id,
    name: p.name,
    price: p.price,
    durationMonths: p.duration_months,
    ticketDiscountPct: p.ticket_discount_pct,
    merchDiscountPct: p.merch_discount_pct,
  };
}

function fromWireMembership(m: WireMembership): MembershipRecord {
  return { id: m.id, plan: fromWirePlan(m.plan), status: m.status, startDate: m.start_date, endDate: m.end_date };
}

function fromWireOrder(o: WireOrder): Order {
  return {
    id: o.id,
    status: o.status,
    subtotal: o.subtotal,
    discount: o.discount,
    total: o.total,
    paymentRef: o.payment_ref,
    createdAt: o.created_at,
    lines: o.lines.map((l) => ({ id: l.id, kind: l.kind, plan: l.plan, qty: l.qty, unitPrice: l.unit_price })),
  };
}

function fromWirePayment(p: WirePayment): Payment {
  return { id: p.id, amount: p.amount, status: p.status, gatewayRef: p.gateway_ref, createdAt: p.created_at };
}

export const realMembershipApi = {
  async listPlans(): Promise<Plan[]> {
    // Plans are few and the contract gives no reason to expect more than one
    // page for Phase 1, so we read the first page only.
    const page = await request<Paginated<WirePlan>>('/plans');
    return page.results.map(fromWirePlan);
  },

  async purchase({ plan, testOutcome, coupon }: PurchaseRequest, idempotencyKey: string): Promise<PurchaseResult> {
    const { status, data: result } = await requestWithStatus<WirePurchaseResult>('/memberships', {
      method: 'POST',
      body: { plan, ...(testOutcome ? { test_outcome: testOutcome } : {}), ...(coupon ? { coupon } : {}) },
      headers: { 'Idempotency-Key': idempotencyKey },
    });
    return {
      order: fromWireOrder(result.order),
      payment: result.payment ? fromWirePayment(result.payment) : null,
      membership: result.membership ? fromWireMembership(result.membership) : null,
      replayed: status === 200,
    };
  },

  async getMyMembership(): Promise<MyMembership> {
    const result = await request<WireMyMembership>('/memberships/me');
    return {
      status: result.status,
      membership: result.membership ? fromWireMembership(result.membership) : null,
      paidUntil: result.paid_until,
      memberQrToken: result.member_qr_token,
    };
  },

  // GAP: the Razorpay endpoints below aren't in docs/API_CONTRACT.md yet —
  // built against the exact shape the demo-polish brief gave: /order takes
  // a purpose + Idempotency-Key and returns what Checkout needs to open;
  // /verify takes our own order_id plus the three razorpay_* fields and
  // returns the same body as a mock-gateway purchase; /cancel just takes
  // our order_id.
  async createRazorpayOrder(planId: number, idempotencyKey: string, coupon?: string): Promise<RazorpayOrderInfo> {
    return fromWireRazorpayOrderInfo(
      await request<WireRazorpayOrderInfo>('/payments/razorpay/order', {
        method: 'POST',
        // The coupon has to go with the order: Razorpay charges what the
        // server prices here, so leaving it out charges the full price.
        body: { purpose: 'membership', plan: planId, ...(coupon ? { coupon } : {}) },
        headers: { 'Idempotency-Key': idempotencyKey },
      }),
    );
  },

  async verifyRazorpayPayment(orderId: number, fields: RazorpayVerifyFields): Promise<PurchaseResult> {
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
      membership: result.membership ? fromWireMembership(result.membership) : null,
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
