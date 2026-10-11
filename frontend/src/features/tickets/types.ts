export type TicketStatus = 'valid' | 'checked_in' | 'cancelled';

export interface TicketEventRef {
  id: number;
  title: string;
  venue: string;
  startsAt: string;
}

export interface TicketTierRef {
  id: number;
  name: string;
}

export interface Ticket {
  id: number;
  code: string;
  qrToken: string;
  status: TicketStatus;
  pricePaid: number; // paise
  event: TicketEventRef;
  tier: TicketTierRef;
  createdAt: string;
}

/** A group pass: one QR that admits everyone bought in the same purchase.
 * Each underlying ticket (one per seat) still exists and still has its own
 * `qr_token`/`code` that works at the door on its own. */
export interface PassEventRef {
  id: number;
  title: string;
  startsAt: string;
  venue: string;
}

export interface PassTierRef {
  id: number;
  name: string;
}

export interface PassTicketRef {
  id: number;
  code: string;
  status: TicketStatus;
}

export interface Pass {
  passId: number;
  event: PassEventRef;
  tier: PassTierRef;
  quantity: number;
  admitted: number;
  remaining: number;
  qrToken: string;
  tickets: PassTicketRef[];
  createdAt: string;
}

export interface PassCheckinHistoryEntry {
  at: string;
  by: string;
  count: number;
}

export interface PassDetail extends Pass {
  order: number;
  holder: { name: string };
  history: PassCheckinHistoryEntry[];
}

export type PaymentTestOutcome = 'success' | 'failure' | 'pending';

export interface PurchaseTicketsRequest {
  tier: number;
  quantity?: number;
  testOutcome?: PaymentTestOutcome;
  coupon?: string;
}

export interface TicketOrder {
  id: number;
  status: 'paid' | 'pending' | 'cancelled';
  subtotal: number;
  discount: number;
  coupon: string | null;
  couponDiscount: number;
  total: number;
  paymentRef: string;
  needsRefund: boolean;
  createdAt: string;
}

export interface TicketPayment {
  id: number;
  amount: number;
  status: 'succeeded' | 'failed' | 'pending';
  gatewayRef: string;
  createdAt: string;
}

export interface PurchaseTicketsResult {
  order: TicketOrder;
  payment: TicketPayment | null;
  tickets: Ticket[];
  /** The group pass for this purchase — one QR that admits everyone bought.
   * `null` only when the order is still `pending` (nothing delivered yet). */
  pass: Pass | null;
  /** True when the server answered 200, not 201: this Idempotency-Key had
   * already paid, and this is that earlier result (nothing new was charged). */
  replayed: boolean;
}
