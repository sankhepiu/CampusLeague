import { ApiRequestError, type Paginated } from '../../api/client';
import { getCurrentMockUser } from '../auth/mockUsers';
import { addMockOrder } from '../orders/mockOrdersStore';
import {
  createMockProduct,
  getMockProduct,
  getMockProductSize,
  listMockProducts,
  reserveMockStock,
  restockMockProduct,
  toPublicProduct,
  updateMockProduct,
} from './mockProductsStore';
import type { PlaceOrderRequest, PlaceOrderResult, Product, ProductDraft, RestockRequest, ShopOrder, ShopOrderLine, ShopPayment } from './types';
import type { RazorpayOrderInfo } from '../payments/types';

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const PAGE_SIZE = 20;

/** See the matching function in features/membership/api.mock.ts — mock
 * mode's payments config always reports gateway: 'mock', so this is never
 * actually reachable. */
function razorpayNotAvailableInMock(): never {
  throw new ApiRequestError({ code: 'not_implemented', message: 'Razorpay is not available in mock mode.' });
}

interface IdempotencyRecord {
  userEmail: string;
  basketKey: string; // sorted "sizeId:qty" pairs, so a different basket with the same key is a reuse
  result: PlaceOrderResult;
}

const IDEMPOTENCY_KEY = 'campusleague.mock.orderIdempotency';

function loadIdempotency(): Record<string, IdempotencyRecord> {
  try {
    const raw = localStorage.getItem(IDEMPOTENCY_KEY);
    if (raw) return JSON.parse(raw) as Record<string, IdempotencyRecord>;
  } catch {
    /* storage unavailable or corrupt */
  }
  return {};
}

function saveIdempotency(store: Record<string, IdempotencyRecord>): void {
  try {
    localStorage.setItem(IDEMPOTENCY_KEY, JSON.stringify(store));
  } catch {
    /* storage unavailable */
  }
}

function basketKeyFor(items: PlaceOrderRequest['items']): string {
  return items.map((i) => `${i.productSize}:${i.quantity ?? 1}`).sort().join(',');
}

const mockGatewayRef = () => `mock_${Date.now().toString(16)}${Math.random().toString(16).slice(2, 10)}`;

function requireUser() {
  const user = getCurrentMockUser();
  if (!user) throw new ApiRequestError({ code: 'not_authenticated', message: 'No active session.' });
  return user;
}

export const mockShopApi = {
  async listProducts(page = 1): Promise<Paginated<Product>> {
    await delay(300);
    const user = getCurrentMockUser();
    const isStaff = !!user?.roles.some((r) => r === 'president' || r === 'treasurer' || r === 'event_manager');
    const visible = listMockProducts().filter((p) => p.active || isStaff);
    const results = visible.map(toPublicProduct);
    const start = (page - 1) * PAGE_SIZE;
    const slice = results.slice(start, start + PAGE_SIZE);
    return { count: results.length, next: start + PAGE_SIZE < results.length ? `?page=${page + 1}` : null, previous: page > 1 ? `?page=${page - 1}` : null, results: slice };
  },

  async getProduct(id: number): Promise<Product> {
    await delay(250);
    const product = getMockProduct(id);
    if (!product) throw new ApiRequestError({ code: 'not_found', message: 'No such product.' });
    if (!product.active) {
      const user = getCurrentMockUser();
      const isStaff = !!user?.roles.some((r) => r === 'president' || r === 'treasurer' || r === 'event_manager');
      if (!isStaff) throw new ApiRequestError({ code: 'not_found', message: 'No such product.' });
    }
    return toPublicProduct(product);
  },

  async createProduct(draft: ProductDraft): Promise<Product> {
    await delay(400);
    return toPublicProduct(createMockProduct(draft));
  },

  async updateProduct(id: number, draft: Partial<ProductDraft>): Promise<Product> {
    await delay(400);
    return toPublicProduct(updateMockProduct(id, draft));
  },

  async restock(id: number, req: RestockRequest): Promise<Product> {
    await delay(350);
    if (req.quantity < 1 || req.quantity > 10000) {
      throw new ApiRequestError({ code: 'validation_error', message: 'Quantity must be between 1 and 10000.', field: 'quantity' });
    }
    return toPublicProduct(restockMockProduct(id, req));
  },

  async placeOrder({ items, testOutcome = 'success' }: PlaceOrderRequest, idempotencyKey: string): Promise<PlaceOrderResult> {
    await delay(700);
    const user = requireUser();

    if (items.length < 1 || items.length > 20) {
      throw new ApiRequestError({ code: 'validation_error', message: 'An order needs 1 to 20 lines.', field: 'items' });
    }
    const seenSizes = new Set<number>();
    for (const item of items) {
      if (seenSizes.has(item.productSize)) {
        throw new ApiRequestError({ code: 'validation_error', message: 'Each size can only appear once in an order.', field: 'items' });
      }
      seenSizes.add(item.productSize);
      const qty = item.quantity ?? 1;
      if (qty < 1 || qty > 10) {
        throw new ApiRequestError({ code: 'validation_error', message: 'Quantity must be between 1 and 10.', field: 'items' });
      }
    }

    const basketKey = basketKeyFor(items);
    const idempotency = loadIdempotency();
    const replay = idempotency[idempotencyKey];
    if (replay) {
      if (replay.userEmail !== user.email || replay.basketKey !== basketKey) {
        throw new ApiRequestError({ code: 'idempotency_key_reused', message: 'This idempotency key already paid for a different basket.' });
      }
      return { ...replay.result, replayed: true };
    }

    // Resolve + validate every line before touching stock, so one bad size
    // refuses the whole basket (matches the contract's one-transaction rule).
    const resolved = items.map((item) => {
      const found = getMockProductSize(item.productSize);
      if (!found || !found.product.active) {
        throw new ApiRequestError({ code: 'product_unavailable', message: 'One of the items in your basket is no longer available.' });
      }
      const qty = item.quantity ?? 1;
      if (found.size.stock < qty) {
        throw new ApiRequestError({
          code: 'out_of_stock',
          message: `${found.product.name} (${found.size.size}): only ${found.size.stock} left, but ${qty} were requested.`,
        });
      }
      return { product: found.product, size: found.size, qty };
    });

    if (testOutcome === 'failure') {
      throw new ApiRequestError({ code: 'payment_failed', message: 'The mock payment gateway declined this attempt.' });
    }

    const orderId = Date.now() + Math.floor(Math.random() * 1000);
    const createdAt = new Date().toISOString();

    if (testOutcome === 'pending') {
      const lines: ShopOrderLine[] = resolved.map((r, i) => ({
        id: orderId + i,
        kind: 'merch',
        productSize: r.size.id,
        qty: r.qty,
        unitPrice: priceForUnit(r.product.id),
        discount: 0,
      }));
      const subtotal = lines.reduce((sum, l) => sum + l.unitPrice * l.qty, 0);
      const order: ShopOrder = { id: orderId, status: 'pending', subtotal, discount: 0, total: subtotal, paymentRef: '', createdAt, lines };
      return { order, payment: null, replayed: false };
    }

    // Success — reserve stock for every line.
    for (const r of resolved) reserveMockStock(r.size.id, r.qty);

    const lines: ShopOrderLine[] = resolved.map((r, i) => ({
      id: orderId + i,
      kind: 'merch',
      productSize: r.size.id,
      qty: r.qty,
      unitPrice: r.product.basePrice,
      discount: (r.product.basePrice - priceForUnit(r.product.id)) * r.qty,
    }));
    const subtotal = lines.reduce((sum, l) => sum + l.unitPrice * l.qty, 0);
    const discount = lines.reduce((sum, l) => sum + l.discount, 0);
    const total = subtotal - discount;

    const gatewayRef = mockGatewayRef();
    const order: ShopOrder = { id: orderId, status: 'paid', subtotal, discount, total, paymentRef: gatewayRef, createdAt, lines };
    const payment: ShopPayment = { id: orderId + lines.length, amount: total, status: 'succeeded', gatewayRef, createdAt };
    const result: PlaceOrderResult = { order, payment, replayed: false };

    idempotency[idempotencyKey] = { userEmail: user.email, basketKey, result };
    saveIdempotency(idempotency);

    addMockOrder(user.email, {
      ...order,
      lines: order.lines.map((l, i) => ({ ...l, label: `${resolved[i].product.name} · ${resolved[i].size.size}`, plan: null, tier: null })),
    });

    return result;
  },

  async createRazorpayOrder(): Promise<RazorpayOrderInfo> {
    razorpayNotAvailableInMock();
  },

  async verifyRazorpayPayment(): Promise<PlaceOrderResult> {
    razorpayNotAvailableInMock();
  },

  async cancelRazorpayPayment(): Promise<void> {
    razorpayNotAvailableInMock();
  },
};

function priceForUnit(productId: number): number {
  const product = getMockProduct(productId);
  return product ? toPublicProduct(product).price : 0;
}
