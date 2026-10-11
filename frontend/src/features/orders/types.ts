export type OrderKind = 'membership' | 'ticket' | 'merch';
export type OrderStatus = 'pending' | 'paid' | 'cancelled';

export interface OrderLine {
  id: number;
  kind: OrderKind;
  /** What was bought, written by the server and ready to display:
   * "Plus membership", "Spring Gala · General", "Skyline Hoodie · M". */
  label: string;
  /** The id matching `kind`; the other two are null. */
  plan: number | null;
  tier: number | null;
  productSize: number | null;
  qty: number;
  unitPrice: number; // paise
  /** Paise, every discount on this line together: sale, member and coupon. */
  discount: number;
  /** Paise: the part of `discount` that came from the order's coupon. */
  couponDiscount: number;
}

export interface Order {
  id: number;
  status: OrderStatus;
  subtotal: number;
  /** Paise, every discount together (sale, member and coupon).
   * `total = subtotal - discount`, always. */
  discount: number;
  /** The coupon code used, or null. */
  coupon: string | null;
  /** Paise: the part of `discount` that came from the coupon; 0 without one. */
  couponDiscount: number;
  total: number;
  /** True only on a cancelled order whose buyer was charged but got nothing. */
  needsRefund: boolean;
  paymentRef: string;
  createdAt: string;
  lines: OrderLine[];
}
