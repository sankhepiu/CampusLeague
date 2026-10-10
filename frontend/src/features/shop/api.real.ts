import { request, requestWithStatus, type Paginated } from '../../api/client';
import type { PlaceOrderRequest, PlaceOrderResult, Product, ProductDraft, ProductSize, RestockRequest, ShopOrder, ShopOrderLine, ShopPayment } from './types';

interface WireProductSize {
  id: number;
  size: ProductSize['size'];
  stock: number;
}

interface WireProduct {
  id: number;
  name: string;
  description: string;
  base_price: number;
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
  total: number;
  payment_ref: string;
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

function fromWireProduct(p: WireProduct): Product {
  return {
    id: p.id,
    name: p.name,
    description: p.description,
    basePrice: p.base_price,
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
    total: o.total,
    paymentRef: o.payment_ref,
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
    if (draft.active !== undefined) body.active = draft.active;
    return fromWireProduct(await request<WireProduct>(`/products/${id}`, { method: 'PATCH', body }));
  },

  async restock(id: number, { size, quantity }: RestockRequest): Promise<Product> {
    return fromWireProduct(await request<WireProduct>(`/products/${id}/restock`, { method: 'POST', body: { size, quantity } }));
  },

  async placeOrder({ items, testOutcome }: PlaceOrderRequest, idempotencyKey: string): Promise<PlaceOrderResult> {
    const { status, data: result } = await requestWithStatus<WirePlaceOrderResult>('/orders', {
      method: 'POST',
      body: {
        items: items.map((i) => ({ product_size: i.productSize, ...(i.quantity !== undefined ? { quantity: i.quantity } : {}) })),
        ...(testOutcome ? { test_outcome: testOutcome } : {}),
      },
      headers: { 'Idempotency-Key': idempotencyKey },
    });
    return { order: fromWireOrder(result.order), payment: result.payment ? fromWirePayment(result.payment) : null, replayed: status === 200 };
  },
};
