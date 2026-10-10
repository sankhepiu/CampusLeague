import type { Order } from './types';

/** Shared localStorage-backed order history, written to by every purchase
 * flow (membership, tickets, shop) on success, so GET /orders/me can show
 * "orders of every kind" the way the real backend's single orders table
 * would. Each flow keeps its own purchase-response/idempotency state too —
 * this is purely the append-only history for the My Orders screen. */

interface StoredOrder extends Order {
  ownerEmail: string;
}

const STORE_KEY = 'campusleague.mock.orders';

function loadStore(): StoredOrder[] {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) return JSON.parse(raw) as StoredOrder[];
  } catch {
    /* storage unavailable or corrupt */
  }
  return [];
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
