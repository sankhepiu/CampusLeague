import { request, type Paginated } from '../../api/client';
import type { MyMembership, Order, Payment, Plan, MembershipRecord, PurchaseRequest, PurchaseResult } from './types';

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

  async purchase({ plan, testOutcome }: PurchaseRequest, idempotencyKey: string): Promise<PurchaseResult> {
    const result = await request<WirePurchaseResult>('/memberships', {
      method: 'POST',
      body: { plan, ...(testOutcome ? { test_outcome: testOutcome } : {}) },
      headers: { 'Idempotency-Key': idempotencyKey },
    });
    return {
      order: fromWireOrder(result.order),
      payment: result.payment ? fromWirePayment(result.payment) : null,
      membership: result.membership ? fromWireMembership(result.membership) : null,
    };
  },

  async getMyMembership(): Promise<MyMembership> {
    const result = await request<WireMyMembership>('/memberships/me');
    return {
      status: result.status,
      membership: result.membership ? fromWireMembership(result.membership) : null,
      paidUntil: result.paid_until,
    };
  },
};
