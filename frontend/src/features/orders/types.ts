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
  discount: number; // paise, total for this line
}

export interface Order {
  id: number;
  status: OrderStatus;
  subtotal: number;
  discount: number;
  total: number;
  paymentRef: string;
  createdAt: string;
  lines: OrderLine[];
}
