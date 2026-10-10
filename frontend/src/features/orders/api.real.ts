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

function fromWireLine(l: WireOrderLine): OrderLine {
  return { id: l.id, kind: l.kind, label: l.label, plan: l.plan, tier: l.tier, productSize: l.product_size, qty: l.qty, unitPrice: l.unit_price, discount: l.discount };
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
    lines: o.lines.map(fromWireLine),
  };
}

export const realOrdersApi = {
  async listMine(page = 1): Promise<Paginated<Order>> {
    const result = await request<Paginated<WireOrder>>('/orders/me', { query: { page } });
    return { ...result, results: result.results.map(fromWireOrder) };
  },
};
