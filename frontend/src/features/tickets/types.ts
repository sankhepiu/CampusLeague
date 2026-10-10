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

export type PaymentTestOutcome = 'success' | 'failure' | 'pending';

export interface PurchaseTicketsRequest {
  tier: number;
  quantity?: number;
  testOutcome?: PaymentTestOutcome;
}

export interface TicketOrder {
  id: number;
  status: 'paid' | 'pending' | 'cancelled';
  subtotal: number;
  discount: number;
  total: number;
  paymentRef: string;
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
  /** True when the server answered 200, not 201: this Idempotency-Key had
   * already paid, and this is that earlier result (nothing new was charged). */
  replayed: boolean;
}
