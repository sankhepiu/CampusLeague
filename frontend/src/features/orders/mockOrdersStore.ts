import type { Order, OrderLine } from './types';

/** Shared localStorage-backed order history, written to by every purchase
 * flow (membership, tickets, shop) on success, so GET /orders/me can show
 * "orders of every kind" the way the real backend's single orders table
 * would. Each flow keeps its own purchase-response/idempotency state too —
 * this is purely the append-only history for the My Orders screen. */

export interface StoredOrder extends Order {
  ownerEmail: string;
}

type MockOrderLineInput = Omit<OrderLine, 'couponDiscount'> & Partial<Pick<OrderLine, 'couponDiscount'>>;

/** What the purchase mocks hand over. The coupon fields are optional, so a
 * flow that knows nothing about coupons still records a valid order. */
export type MockOrderInput = Omit<Order, 'coupon' | 'couponDiscount' | 'needsRefund' | 'lines'> &
  Partial<Pick<Order, 'coupon' | 'couponDiscount' | 'needsRefund'>> & { lines: MockOrderLineInput[] };

/** Fills in what an order saved by an older build (or by a flow without
 * coupons) leaves out, so every order read from the store is a full Order. */
function normalise<T extends MockOrderInput>(order: T): T & Order {
  return {
    ...order,
    coupon: order.coupon ?? null,
    couponDiscount: order.couponDiscount ?? 0,
    needsRefund: order.needsRefund ?? false,
    lines: order.lines.map((line) => ({
      ...line,
      // Orders saved by an older build of the mock have no label.
      label: line.label ?? FALLBACK_LABEL[line.kind],
      couponDiscount: line.couponDiscount ?? 0,
    })),
  };
}

const STORE_KEY = 'campusleague.mock.orders';
const FALLBACK_LABEL: Record<Order['lines'][number]['kind'], string> = { membership: 'Membership', ticket: 'Ticket', merch: 'Merchandise' };

/** A handful of historical membership and merch orders so the finance
 * ledger (Phase 5) has more than ticket revenue to show on a fresh profile —
 * membership/shop purchases made through the live flows land here too, but
 * nothing pre-dates this session otherwise. Attributed to synthetic
 * "seed.*" buyers, matching the convention in tickets/mockTicketsStore.ts,
 * so they never show up in a real demo account's own My Orders history. */
function seedOrders(): StoredOrder[] {
  const daysAgo = (n: number) => new Date(Date.now() - n * 86_400_000).toISOString();
  const seeds: Array<MockOrderInput & { ownerEmail: string }> = [
    {
      id: 9001, ownerEmail: 'seed.member1@campusleague.dev', status: 'paid', subtotal: 50000, discount: 0, total: 50000,
      paymentRef: 'seed-gw-9001', createdAt: daysAgo(40),
      lines: [{ id: 9001, kind: 'membership', label: 'Basic membership', plan: 1, tier: null, productSize: null, qty: 1, unitPrice: 50000, discount: 0 }],
    },
    {
      id: 9002, ownerEmail: 'seed.member2@campusleague.dev', status: 'paid', subtotal: 50000, discount: 0, total: 50000,
      paymentRef: 'seed-gw-9002', createdAt: daysAgo(25),
      lines: [{ id: 9002, kind: 'membership', label: 'Basic membership', plan: 1, tier: null, productSize: null, qty: 1, unitPrice: 50000, discount: 0 }],
    },
    {
      id: 9003, ownerEmail: 'seed.member3@campusleague.dev', status: 'paid', subtotal: 90000, discount: 0, total: 90000,
      paymentRef: 'seed-gw-9003', createdAt: daysAgo(12),
      lines: [{ id: 9003, kind: 'membership', label: 'Plus membership', plan: 2, tier: null, productSize: null, qty: 1, unitPrice: 90000, discount: 0 }],
    },
    {
      id: 9004, ownerEmail: 'seed.shopper1@campusleague.dev', status: 'paid', subtotal: 240000, discount: 0, total: 240000,
      paymentRef: 'seed-gw-9004', createdAt: daysAgo(20),
      lines: [{ id: 9004, kind: 'merch', label: 'Skyline Hoodie · M', plan: null, tier: null, productSize: 2, qty: 2, unitPrice: 120000, discount: 0 }],
    },
    {
      id: 9005, ownerEmail: 'seed.shopper2@campusleague.dev', status: 'paid', subtotal: 120000, discount: 0, total: 120000,
      paymentRef: 'seed-gw-9005', createdAt: daysAgo(8),
      lines: [{ id: 9005, kind: 'merch', label: 'Campus Tee · M', plan: null, tier: null, productSize: 6, qty: 3, unitPrice: 40000, discount: 0 }],
    },
    // One order with a coupon, so the finance mock has a discounted sale:
    // 2 x 800.00 = 1,600.00, MERCH20 takes 20% capped at 150.00.
    {
      id: 9006, ownerEmail: 'seed.shopper3@campusleague.dev', status: 'paid', subtotal: 160000, discount: 15000, total: 145000,
      coupon: 'MERCH20', couponDiscount: 15000, paymentRef: 'seed-gw-9006', createdAt: daysAgo(3),
      lines: [{ id: 9006, kind: 'merch', label: 'Skyline Hoodie · L', plan: null, tier: null, productSize: 3, qty: 2, unitPrice: 80000, discount: 15000, couponDiscount: 15000 }],
    },
  ];
  return seeds.map(normalise);
}

function loadStore(): StoredOrder[] {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) return (JSON.parse(raw) as Array<MockOrderInput & { ownerEmail: string }>).map(normalise);
  } catch {
    /* storage unavailable or corrupt */
  }
  const seeded = seedOrders();
  saveStore(seeded);
  return seeded;
}

function saveStore(orders: StoredOrder[]): void {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(orders));
  } catch {
    /* storage unavailable */
  }
}

export function addMockOrder(ownerEmail: string, order: MockOrderInput): void {
  const store = loadStore();
  store.push(normalise({ ...order, ownerEmail }));
  saveStore(store);
}

export function listMockOrdersForUser(email: string): Order[] {
  return loadStore()
    .filter((o) => o.ownerEmail === email)
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
    .map(({ ownerEmail: _ownerEmail, ...order }) => order);
}

/** Every order across every buyer, owner email kept — the finance ledger
 * mock needs both the line data and who bought it (for trace labels). */
export function listAllMockOrders(): StoredOrder[] {
  return loadStore();
}
