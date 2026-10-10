export type PaymentGateway = 'mock' | 'razorpay';

export interface PaymentsConfig {
  gateway: PaymentGateway;
}

/** What POST /payments/razorpay/order hands back — enough to open the
 * Razorpay Checkout modal directly. Shared by every purchase flow
 * (membership, tickets, merch), each of which gets there with its own
 * purpose-specific request body. */
export interface RazorpayOrderInfo {
  /** Our own order id — not Razorpay's — passed back to /verify and /cancel. */
  orderId: number;
  razorpayOrderId: string;
  key: string;
  amount: number; // paise
  currency: string;
  name: string;
  description: string;
  prefill: { name: string; email: string };
}

/** The three razorpay_* fields the Checkout success handler receives. */
export interface RazorpayVerifyFields {
  razorpayOrderId: string;
  razorpayPaymentId: string;
  razorpaySignature: string;
}
