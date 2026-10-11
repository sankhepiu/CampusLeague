import { request, requestWithStatus, type Paginated } from '../../api/client';
import type { PlaceOrderRequest, PlaceOrderResult, Product, ProductDraft, ProductSize, RestockRequest, ShopOrder, ShopOrderLine, ShopPayment } from './types';
import type { RazorpayOrderInfo, RazorpayVerifyFields } from '../payments/types';

interface WireProductSize {
  id: number;
  size: ProductSize['size'];
  stock: number;
}

interface WireProduct {
  id: number;
  name: string;
  description: string;
  category: Product['category'];
  base_price: number;
  sale_pct: number;
  price: number;
  image_url: string | null;
  active: boolean;
  sizes: WireProductSize[];
}

interface WireOrderLine {
  id: number;
  kind: 'merch';
  product_size: number;
  qty: number;
  unit_price: number;
  discount: number;
}

interface WireOrder {
  id: number;
  status: ShopOrder['status'];
  subtotal: number;
  discount: number;
  coupon: string | null;
  coupon_discount: number;
  total: number;
  payment_ref: string;
  needs_refund: boolean;
  created_at: string;
  lines: WireOrderLine[];
}

interface WirePayment {
  id: number;
  amount: number;
  status: ShopPayment['status'];
  gateway_ref: string;
  created_at: string;
}

interface WirePlaceOrderResult {
  order: WireOrder;
  payment: WirePayment | null;
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

function fromWireProduct(p: WireProduct): Product {
  return {
    id: p.id,
    name: p.name,
    description: p.description,
    category: p.category,
    basePrice: p.base_price,
    salePct: p.sale_pct,
    price: p.price,
    imageUrl: p.image_url,
    active: p.active,
    sizes: p.sizes.map((s) => ({ id: s.id, size: s.size, stock: s.stock })),
  };
}

function fromWireOrderLine(l: WireOrderLine): ShopOrderLine {
  return { id: l.id, kind: l.kind, productSize: l.product_size, qty: l.qty, unitPrice: l.unit_price, discount: l.discount };
}

function fromWireOrder(o: WireOrder): ShopOrder {
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
    lines: o.lines.map(fromWireOrderLine),
  };
}

function fromWirePayment(p: WirePayment): ShopPayment {
  return { id: p.id, amount: p.amount, status: p.status, gatewayRef: p.gateway_ref, createdAt: p.created_at };
}

export const realShopApi = {
  async listProducts(page = 1): Promise<Paginated<Product>> {
    const result = await request<Paginated<WireProduct>>('/products', { query: { page } });
    return { ...result, results: result.results.map(fromWireProduct) };
  },

  async getProduct(id: number): Promise<Product> {
    return fromWireProduct(await request<WireProduct>(`/products/${id}`));
  },

  async createProduct(draft: ProductDraft): Promise<Product> {
    return fromWireProduct(
      await request<WireProduct>('/products', {
        method: 'POST',
        body: {
          name: draft.name,
          base_price: draft.basePrice,
          ...(draft.description !== undefined ? { description: draft.description } : {}),
          ...(draft.category !== undefined ? { category: draft.category } : {}),
          ...(draft.salePct !== undefined ? { sale_pct: draft.salePct } : {}),
          ...(draft.active !== undefined ? { active: draft.active } : {}),
        },
      }),
    );
  },

  async updateProduct(id: number, draft: Partial<ProductDraft>): Promise<Product> {
    const body: Record<string, unknown> = {};
    if (draft.name !== undefined) body.name = draft.name;
    if (draft.basePrice !== undefined) body.base_price = draft.basePrice;
    if (draft.description !== undefined) body.description = draft.description;
    if (draft.category !== undefined) body.category = draft.category;
    if (draft.salePct !== undefined) body.sale_pct = draft.salePct;
    if (draft.active !== undefined) body.active = draft.active;
    return fromWireProduct(await request<WireProduct>(`/products/${id}`, { method: 'PATCH', body }));
  },

  async restock(id: number, { size, quantity }: RestockRequest): Promise<Product> {
    return fromWireProduct(await request<WireProduct>(`/products/${id}/restock`, { method: 'POST', body: { size, quantity } }));
  },

  async placeOrder({ items, testOutcome, coupon }: PlaceOrderRequest, idempotencyKey: string): Promise<PlaceOrderResult> {
    const { status, data: result } = await requestWithStatus<WirePlaceOrderResult>('/orders', {
      method: 'POST',
      body: {
        items: items.map((i) => ({ product_size: i.productSize, ...(i.quantity !== undefined ? { quantity: i.quantity } : {}) })),
        ...(testOutcome ? { test_outcome: testOutcome } : {}),
        ...(coupon ? { coupon } : {}),
      },
      headers: { 'Idempotency-Key': idempotencyKey },
    });
    return { order: fromWireOrder(result.order), payment: result.payment ? fromWirePayment(result.payment) : null, replayed: status === 200 };
  },

  // GAP: not yet in docs/API_CONTRACT.md — see the matching comment in
  // features/membership/api.real.ts for the shape this was built against.
  async createRazorpayOrder(items: PlaceOrderRequest['items'], idempotencyKey: string, coupon?: string): Promise<RazorpayOrderInfo> {
    return fromWireRazorpayOrderInfo(
      await request<WireRazorpayOrderInfo>('/payments/razorpay/order', {
        method: 'POST',
        // The coupon has to go with the order: Razorpay charges what the
        // server prices here, so leaving it out charges the full amount.
        body: {
          purpose: 'merch',
          items: items.map((i) => ({ product_size: i.productSize, ...(i.quantity !== undefined ? { quantity: i.quantity } : {}) })),
          ...(coupon ? { coupon } : {}),
        },
        headers: { 'Idempotency-Key': idempotencyKey },
      }),
    );
  },

  async verifyRazorpayPayment(orderId: number, fields: RazorpayVerifyFields): Promise<PlaceOrderResult> {
    const { status, data: result } = await requestWithStatus<WirePlaceOrderResult>('/payments/razorpay/verify', {
      method: 'POST',
      body: {
        order_id: orderId,
        razorpay_order_id: fields.razorpayOrderId,
        razorpay_payment_id: fields.razorpayPaymentId,
        razorpay_signature: fields.razorpaySignature,
      },
    });
    return { order: fromWireOrder(result.order), payment: result.payment ? fromWirePayment(result.payment) : null, replayed: status === 200 };
  },

  async cancelRazorpayPayment(orderId: number): Promise<void> {
    await request('/payments/razorpay/cancel', { method: 'POST', body: { order_id: orderId } });
  },
};
