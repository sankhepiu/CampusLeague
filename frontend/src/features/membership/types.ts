export interface Plan {
  id: number;
  name: string;
  price: number; // paise
  durationMonths: number;
  ticketDiscountPct: number;
  merchDiscountPct: number;
}

export type MembershipRecordStatus = 'pending' | 'active' | 'lapsed' | 'cancelled';

export interface MembershipRecord {
  id: number;
  plan: Plan;
  status: MembershipRecordStatus;
  startDate: string; // YYYY-MM-DD
  endDate: string;
}

export interface OrderLine {
  id: number;
  kind: string;
  plan: number;
  qty: number;
  unitPrice: number;
}

export type OrderStatus = 'paid' | 'pending' | 'cancelled';

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

export type PaymentStatus = 'succeeded' | 'failed' | 'pending';

export interface Payment {
  id: number;
  amount: number;
  status: PaymentStatus;
  gatewayRef: string;
  createdAt: string;
}

/** Mock-gateway switch the contract defines on POST /memberships. */
export type PaymentTestOutcome = 'success' | 'failure' | 'pending';

export interface PurchaseRequest {
  plan: number;
  testOutcome?: PaymentTestOutcome;
}

export interface PurchaseResult {
  order: Order;
  payment: Payment | null;
  membership: MembershipRecord | null;
}

export interface MyMembership {
  status: 'active' | 'lapsed' | 'none';
  membership: MembershipRecord | null;
  paidUntil: string | null;
  /** QR content for the member card, when there's an active/lapsed
   * membership to show one for; `null` otherwise. */
  memberQrToken: string | null;
}
