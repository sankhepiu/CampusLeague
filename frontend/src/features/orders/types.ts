export type OrderKind = 'membership' | 'ticket' | 'merch';
export type OrderStatus = 'pending' | 'paid' | 'cancelled';

export interface OrderLine {
  id: number;
  kind: OrderKind;
  /** GAP: the contract's order-line shape only carries bare ids (not names)
   * for whichever of these three matches `kind` — there's no endpoint this
   * phase asks for that would resolve a plan/tier/product_size id back to a
   * human name from here, so the UI shows the kind + id, never a fabricated
   * name. See OrdersPage. */
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
