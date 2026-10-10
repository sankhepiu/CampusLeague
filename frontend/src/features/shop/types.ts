export type SizeLabel = 'S' | 'M' | 'L' | 'XL';

export interface ProductSize {
  id: number;
  size: SizeLabel;
  stock: number;
}

export interface Product {
  id: number;
  name: string;
  description: string;
  basePrice: number; // paise, before member discount
  price: number; // paise — what the caller pays now (server-decided)
  image: string; // "" if none
  active: boolean;
  sizes: ProductSize[]; // always S, M, L, XL in that order
}

export interface ProductDraft {
  name: string;
  basePrice: number;
  description?: string;
  image?: string;
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
  total: number;
  paymentRef: string;
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
}
