import type { Order } from './types';

/** Shared localStorage-backed order history, written to by every purchase
 * flow (membership, tickets, shop) on success, so GET /orders/me can show
 * "orders of every kind" the way the real backend's single orders table
 * would. Each flow keeps its own purchase-response/idempotency state too —
 * this is purely the append-only history for the My Orders screen. */

export interface StoredOrder extends Order {
  ownerEmail: string;
}

const STORE_KEY = 'campusleague.mock.orders';

/** A handful of historical membership and merch orders so the finance
 * ledger (Phase 5) has more than ticket revenue to show on a fresh profile —
 * membership/shop purchases made through the live flows land here too, but
 * nothing pre-dates this session otherwise. Attributed to synthetic
 * "seed.*" buyers, matching the convention in tickets/mockTicketsStore.ts,
 * so they never show up in a real demo account's own My Orders history. */
function seedOrders(): StoredOrder[] {
  const daysAgo = (n: number) => new Date(Date.now() - n * 86_400_000).toISOString();
  return [
    {
      id: 9001, ownerEmail: 'seed.member1@campusleague.dev', status: 'paid', subtotal: 50000, discount: 0, total: 50000,
      paymentRef: 'seed-gw-9001', createdAt: daysAgo(40),
      lines: [{ id: 9001, kind: 'membership', plan: 1, tier: null, productSize: null, qty: 1, unitPrice: 50000, discount: 0 }],
    },
    {
      id: 9002, ownerEmail: 'seed.member2@campusleague.dev', status: 'paid', subtotal: 50000, discount: 0, total: 50000,
      paymentRef: 'seed-gw-9002', createdAt: daysAgo(25),
      lines: [{ id: 9002, kind: 'membership', plan: 1, tier: null, productSize: null, qty: 1, unitPrice: 50000, discount: 0 }],
    },
    {
      id: 9003, ownerEmail: 'seed.member3@campusleague.dev', status: 'paid', subtotal: 90000, discount: 0, total: 90000,
      paymentRef: 'seed-gw-9003', createdAt: daysAgo(12),
      lines: [{ id: 9003, kind: 'membership', plan: 2, tier: null, productSize: null, qty: 1, unitPrice: 90000, discount: 0 }],
    },
    {
      id: 9004, ownerEmail: 'seed.shopper1@campusleague.dev', status: 'paid', subtotal: 240000, discount: 0, total: 240000,
      paymentRef: 'seed-gw-9004', createdAt: daysAgo(20),
      lines: [{ id: 9004, kind: 'merch', plan: null, tier: null, productSize: 2, qty: 2, unitPrice: 120000, discount: 0 }],
    },
    {
      id: 9005, ownerEmail: 'seed.shopper2@campusleague.dev', status: 'paid', subtotal: 120000, discount: 0, total: 120000,
      paymentRef: 'seed-gw-9005', createdAt: daysAgo(8),
      lines: [{ id: 9005, kind: 'merch', plan: null, tier: null, productSize: 6, qty: 3, unitPrice: 40000, discount: 0 }],
    },
  ];
}

function loadStore(): StoredOrder[] {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) return JSON.parse(raw) as StoredOrder[];
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

export function addMockOrder(ownerEmail: string, order: Order): void {
  const store = loadStore();
  store.push({ ...order, ownerEmail });
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
