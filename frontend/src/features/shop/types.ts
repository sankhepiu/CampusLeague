export type SizeLabel = 'S' | 'M' | 'L' | 'XL' | 'ONE';
export type ProductCategory = 'apparel' | 'accessories' | 'stationery' | 'drinkware';

export interface ProductSize {
  id: number;
  size: SizeLabel;
  stock: number;
}

export interface Product {
  id: number;
  name: string;
  description: string;
  category: ProductCategory;
  basePrice: number; // paise, before any discount
  salePct: number; // 0-90: percent off for everyone, 0 means not on sale
  price: number; // paise — what the caller pays now (server-decided)
  /** Path relative to the site root (`/media/products/<file>.png`), loaded
   * through the dev server's /media proxy; `null` when there is no picture.
   * Set by the server only: there is no upload endpoint. */
  imageUrl: string | null;
  active: boolean;
  /** S/M/L/XL in that order for clothing; a single ONE entry for anything
   * that doesn't come in sizes — don't show a size picker for that case. */
  sizes: ProductSize[];
}

export interface ProductDraft {
  name: string;
  basePrice: number;
  description?: string;
  category?: ProductCategory;
  salePct?: number;
  active?: boolean;
}

export interface RestockRequest {
  size: SizeLabel;
  quantity: number; // 1 to 10000
}

export type PaymentTestOutcome = 'success' | 'failure' | 'pending';

export interface OrderItemRequest {
  productSize: number;
  quantity?: number;
}

export interface PlaceOrderRequest {
  items: OrderItemRequest[];
  testOutcome?: PaymentTestOutcome;
  coupon?: string;
}

export interface ShopOrderLine {
  id: number;
  kind: 'merch';
  productSize: number;
  qty: number;
  unitPrice: number;
  discount: number;
}

export interface ShopOrder {
  id: number;
  status: 'pending' | 'paid' | 'cancelled';
  subtotal: number;
  discount: number;
  coupon: string | null;
  couponDiscount: number;
  total: number;
  paymentRef: string;
  needsRefund: boolean;
  createdAt: string;
  lines: ShopOrderLine[];
}

export interface ShopPayment {
  id: number;
  amount: number;
  status: 'succeeded' | 'failed' | 'pending';
  gatewayRef: string;
  createdAt: string;
}

export interface PlaceOrderResult {
  order: ShopOrder;
  payment: ShopPayment | null;
  /** True when the server answered 200, not 201: this Idempotency-Key had
   * already paid, and this is that earlier result (nothing new was charged). */
  replayed: boolean;
}
