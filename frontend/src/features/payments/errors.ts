import type { ApiError } from '../../api/client';

/** Friendlier wording for the two Razorpay-flow error codes the brief calls
 * out specifically; everything else falls back to the server's own message. */
export function razorpayErrorMessage(err: ApiError): string {
  if (err.code === 'sold_out') return "Sold out — you'll be refunded.";
  if (err.code === 'gateway_unavailable') return 'Payment service unreachable, try again.';
  return err.message;
}
