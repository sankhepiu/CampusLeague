import { request, type Paginated } from '../../api/client';
import type { Order, OrderLine } from './types';

interface WireOrderLine {
  id: number;
  kind: OrderLine['kind'];
  label: string;
  plan: number | null;
  tier: number | null;
  product_size: number | null;
  qty: number;
  unit_price: number;
  discount: number;
  coupon_discount?: number;
}

interface WireOrder {
  id: number;
  status: Order['status'];
  subtotal: number;
  discount: number;
  coupon?: string | null;
  coupon_discount?: number;
  total: number;
  needs_refund?: boolean;
  payment_ref: string;
  created_at: string;
  lines: WireOrderLine[];
}

function fromWireLine(l: WireOrderLine): OrderLine {
  return { id: l.id, kind: l.kind, label: l.label, plan: l.plan, tier: l.tier, productSize: l.product_size, qty: l.qty, unitPrice: l.unit_price, discount: l.discount, couponDiscount: l.coupon_discount ?? 0 };
}

function fromWireOrder(o: WireOrder): Order {
  return {
    id: o.id,
    status: o.status,
    subtotal: o.subtotal,
    discount: o.discount,
    // Optional on the wire so a backend from before coupons still works.
    coupon: o.coupon ?? null,
    couponDiscount: o.coupon_discount ?? 0,
    total: o.total,
    needsRefund: o.needs_refund ?? false,
    paymentRef: o.payment_ref,
    createdAt: o.created_at,
    lines: o.lines.map(fromWireLine),
  };
}

export const realOrdersApi = {
  async listMine(page = 1): Promise<Paginated<Order>> {
    const result = await request<Paginated<WireOrder>>('/orders/me', { query: { page } });
    return { ...result, results: result.results.map(fromWireOrder) };
  },
};
