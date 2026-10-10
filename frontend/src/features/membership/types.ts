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
  /** True when the server answered 200, not 201: this Idempotency-Key had
   * already paid, and this is that earlier result (nothing new was charged). */
  replayed: boolean;
}

export interface MyMembership {
  status: 'active' | 'lapsed' | 'none';
  membership: MembershipRecord | null;
  paidUntil: string | null;
  /** The member card: an opaque, server-signed string to render as a QR code
   * exactly as received. `null` for someone who has never been a member. A
   * lapsed member still has one (it scans as "not a member"). */
  memberQrToken: string | null;
}
