import type { ApiError } from '../../api/client';

/** The mock gateway's switch, sent as `test_outcome` on every purchase. */
export type PaymentTestOutcome = 'success' | 'failure' | 'pending';

/** Errors where pressing "Try Again" with the same request cannot help: the
 * seats or stock are gone, sales are closed, or the key was already used for
 * something else. A declined payment or a network failure can be retried. */
const NOT_RETRYABLE = new Set(['sold_out', 'sales_closed', 'out_of_stock', 'product_unavailable', 'idempotency_key_reused', 'validation_error']);

export function isRetryablePaymentError(error: ApiError): boolean {
  return !NOT_RETRYABLE.has(error.code);
}
