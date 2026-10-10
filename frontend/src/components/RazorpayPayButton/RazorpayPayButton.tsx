import { useState } from 'react';
import { Money } from '../Money/Money';
import { Spinner } from '../Spinner/Spinner';
import type { ApiError } from '../../api/client';
import { loadRazorpayCheckout, openRazorpayCheckout } from '../../core/utils/razorpayCheckout';
import type { RazorpayOrderInfo, RazorpayVerifyFields } from '../../features/payments/types';
import styles from './RazorpayPayButton.module.scss';

interface RazorpayPayButtonProps {
  amountPaise: number;
  disabled?: boolean;
  /** Creates the pending order server-side (purpose-specific per caller —
   * membership plan, ticket tier + quantity, or merch items) and returns
   * what's needed to open the Checkout modal. */
  createOrder: () => Promise<RazorpayOrderInfo>;
  /** Called from the Checkout success handler with our own order id and the
   * three razorpay_* fields; the caller does its own purpose-specific
   * POST /payments/razorpay/verify and updates its own success/pending UI. */
  onVerified: (orderId: number, fields: RazorpayVerifyFields) => Promise<void>;
  /** Modal was dismissed without paying — the caller calls its own
   * POST /payments/razorpay/cancel and shows "payment cancelled". */
  onCancelled: (orderId: number) => void;
  onError: (err: ApiError) => void;
}

/** The Razorpay equivalent of the mock gateway's "Pay (Test Mode)" button —
 * swapped in on every purchase screen (membership, tickets, cart) once
 * GET /payments/config reports gateway: "razorpay". Orchestrates the
 * Checkout SDK only; all business logic (creating the order, verifying the
 * payment, handling cancellation) stays with the caller, same as the mock
 * flow keeps its own checkout logic in each page. */
export function RazorpayPayButton({ amountPaise, disabled, createOrder, onVerified, onCancelled, onError }: RazorpayPayButtonProps) {
  const [loading, setLoading] = useState(false);

  const pay = async () => {
    setLoading(true);
    try {
      await loadRazorpayCheckout();
      const order = await createOrder();
      const checkout = openRazorpayCheckout({
        key: order.key,
        amount: order.amount,
        currency: order.currency,
        name: order.name,
        description: order.description,
        order_id: order.razorpayOrderId,
        prefill: order.prefill,
        handler: (response) => {
          void onVerified(order.orderId, {
            razorpayOrderId: response.razorpay_order_id,
            razorpayPaymentId: response.razorpay_payment_id,
            razorpaySignature: response.razorpay_signature,
          })
            .catch((err) => onError(err as ApiError))
            .finally(() => setLoading(false));
        },
        modal: {
          ondismiss: () => {
            setLoading(false);
            onCancelled(order.orderId);
          },
        },
      });
      checkout.on('payment.failed', () => setLoading(false));
      checkout.open();
    } catch (err) {
      setLoading(false);
      onError(err as ApiError);
    }
  };

  return (
    <div className={styles.wrap}>
      <span className={styles.badge}>Razorpay Test Mode</span>
      <button type="button" className={styles.button} onClick={() => void pay()} disabled={disabled || loading}>
        {loading ? (
          <Spinner size={16} label="Processing" />
        ) : (
          <>
            Pay <Money paise={amountPaise} />
          </>
        )}
      </button>
    </div>
  );
}
