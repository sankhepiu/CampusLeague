import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { EmptyState } from '../../components/EmptyState/EmptyState';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { Money } from '../../components/Money/Money';
import { TextInput } from '../../components/FormField/TextInput';
import { ReplayNote, TestPayment } from '../../components/TestPayment/TestPayment';
import { isRetryablePaymentError } from '../../components/TestPayment/paymentErrors';
import { RazorpayPayButton } from '../../components/RazorpayPayButton/RazorpayPayButton';
import type { ApiError } from '../../api/client';
import { useAuth } from '../../core/hooks/useAuth';
import { useCart } from '../../core/hooks/useCart';
import { usePaymentsConfig } from '../../core/hooks/usePaymentsConfig';
import { accentVarForFeature } from '../../core/config/accents';
import { shopApi } from './api';
import { couponsApi } from '../coupons/api';
import type { CouponValidateResponse } from '../coupons/types';
import { razorpayErrorMessage } from '../payments/errors';
import type { RazorpayVerifyFields } from '../payments/types';
import type { PaymentTestOutcome, PlaceOrderResult } from './types';
import { LIMIT_REACHED_MESSAGE, MAX_PER_ITEM } from './limits';
import { pickupOrDefault } from './pickup';
import styles from './CartPage.module.scss';

type CheckoutPhase = 'idle' | 'submitting' | 'success' | 'pending' | 'error' | 'cancelled';

export function CartPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { items, updateQuantity, removeItem, clear, estimatedSubtotal } = useCart();
  const { gateway } = usePaymentsConfig();

  // Two steps: review the cart, then the (test mode) payment screen.
  const [atPayment, setAtPayment] = useState(false);
  const [testOutcome, setTestOutcome] = useState<PaymentTestOutcome>('success');
  const [idempotencyKey, setIdempotencyKey] = useState<string | null>(null);
  const [phase, setPhase] = useState<CheckoutPhase>('idle');
  const [error, setError] = useState<ApiError | null>(null);
  const [result, setResult] = useState<PlaceOrderResult | null>(null);

  // Order summary breakdown: subtotal (base prices) → sale → member discount
  // → coupon → total. Sale/member are estimates snapshotted when each item
  // was added to the cart; the server works out the authoritative figures.
  const breakdown = useMemo(() => {
    const baseSubtotal = items.reduce((sum, i) => sum + i.unitBasePriceEstimate * i.quantity, 0);
    const saleDiscount = items.reduce((sum, i) => sum + Math.max(0, i.unitBasePriceEstimate - i.unitSalePriceEstimate) * i.quantity, 0);
    const memberDiscount = items.reduce((sum, i) => sum + Math.max(0, i.unitSalePriceEstimate - i.unitPriceEstimate) * i.quantity, 0);
    return { baseSubtotal, saleDiscount, memberDiscount, preCouponTotal: estimatedSubtotal };
  }, [items, estimatedSubtotal]);

  const [couponCode, setCouponCode] = useState('');
  const [couponResult, setCouponResult] = useState<CouponValidateResponse | null>(null);
  const [couponChecking, setCouponChecking] = useState(false);

  useEffect(() => {
    const code = couponCode.trim();
    if (!code) {
      setCouponResult(null);
      return;
    }
    setCouponChecking(true);
    const timer = setTimeout(() => {
      couponsApi
        .validate({ code, appliesTo: 'merch', amount: breakdown.preCouponTotal })
        .then(setCouponResult)
        .catch(() => setCouponResult({ valid: false, discount: 0, finalAmount: breakdown.preCouponTotal, reason: null, message: 'Could not check this coupon.' }))
        .finally(() => setCouponChecking(false));
    }, 400);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [couponCode, breakdown.preCouponTotal]);

  const couponDiscount = couponResult?.valid ? couponResult.discount : 0;
  const appliedCoupon = couponResult?.valid ? couponCode.trim().toUpperCase() : undefined;
  const grandTotal = breakdown.preCouponTotal - couponDiscount;
  const pickupLocations = [...new Set(items.map((i) => pickupOrDefault(i.pickupLocation)))];

  const checkout = async (key: string) => {
    setPhase('submitting');
    setError(null);
    try {
      const res = await shopApi.placeOrder(
        { items: items.map((i) => ({ productSize: i.productSizeId, quantity: i.quantity })), testOutcome, coupon: appliedCoupon },
        key,
      );
      setResult(res);
      if (res.order.status === 'pending') {
        setPhase('pending');
      } else {
        setPhase('success');
        clear();
      }
    } catch (err) {
      setError(err as ApiError);
      setPhase('error');
    }
  };

  // A fresh "Pay" press is a new logical attempt and always gets a new key.
  // "Reuse the same key on retry" only applies to the explicit Try Again
  // button below, which retries this exact failed attempt — not to a later,
  // independent press of Pay (e.g. after adjusting the cart post-sold-out).
  // Double-submission from a literal double click is prevented separately,
  // by disabling the button while phase === 'submitting'.
  const goToPayment = () => {
    if (!user) {
      navigate('/login', { state: { from: '/shop/cart' } });
      return;
    }
    setError(null);
    setPhase('idle');
    setAtPayment(true);
  };

  const onPay = () => {
    const key = crypto.randomUUID();
    setIdempotencyKey(key);
    void checkout(key);
  };

  const retry = () => {
    if (idempotencyKey) void checkout(idempotencyKey);
  };

  const onRazorpayVerified = async (orderId: number, fields: RazorpayVerifyFields) => {
    setPhase('submitting');
    setError(null);
    try {
      const res = await shopApi.verifyRazorpayPayment(orderId, fields);
      setResult(res);
      setPhase('success');
      clear();
    } catch (err) {
      setError(err as ApiError);
      setPhase('error');
    }
  };

  const onRazorpayCancelled = (orderId: number) => {
    void shopApi.cancelRazorpayPayment(orderId);
    setPhase('cancelled');
  };

  const onRazorpayError = (err: ApiError) => {
    setError(err);
    setPhase('error');
  };

  if (phase === 'success' && result) {
    return (
      <PageShell title="Cart" background="dotted">
        <Panel accent="var(--cl-green)" className={styles.successBox}>
          <p>
            <strong>Payment successful!</strong>
          </p>
          {result.replayed && <ReplayNote />}
          <p>
            Subtotal <Money paise={result.order.subtotal} /> · Discount <Money paise={result.order.discount} />
            {result.order.coupon && (
              <>
                {' '}
                (incl. <Money paise={result.order.couponDiscount} /> from {result.order.coupon})
              </>
            )}{' '}
            · Total <Money paise={result.order.total} />
          </p>
          <Link to="/orders" className={styles.button} style={{ textDecoration: 'none', display: 'inline-block', marginTop: '1rem' }}>
            View My Orders
          </Link>
        </Panel>
      </PageShell>
    );
  }

  if (items.length === 0) {
    return (
      <PageShell title="Cart" background="dotted">
        <Panel>
          <EmptyState icon="chest" title="Your cart is empty" message="Add something from the shop first." action={<Link to="/shop">Browse Shop</Link>} />
        </Panel>
      </PageShell>
    );
  }

  if (atPayment) {
    const busy = phase === 'submitting';
    return (
      <PageShell title="Payment" background="dotted">
        <Panel accent="var(--cl-gold)" className={styles.summary}>
          <ul className={styles.payLines}>
            {items.map((item) => (
              <li key={item.productSizeId} className={styles.summaryRow}>
                <span>
                  {item.productName} · {item.sizeLabel} × {item.quantity}
                </span>
                <Money paise={item.unitPriceEstimate * item.quantity} />
              </li>
            ))}
          </ul>
          <OrderSummaryBreakdown breakdown={breakdown} couponCode={appliedCoupon} couponDiscount={couponDiscount} total={grandTotal} />
          <p className={styles.estimateNote}>Collect from: {pickupLocations.join(' · ')}</p>
          <p className={styles.estimateNote}>The server works out the final price and any member discount when you pay.</p>

          {phase === 'pending' && (
            <p className={styles.pendingNote} role="status">
              <strong>Payment pending.</strong> The gateway has not confirmed it, so no stock is held and nothing was charged. You can pay
              again.
            </p>
          )}
          {phase === 'cancelled' && (
            <p className={styles.pendingNote} role="status">
              <strong>Payment cancelled.</strong> No stock was held and nothing was charged.
            </p>
          )}

          {gateway === 'razorpay' ? (
            <>
              {phase === 'error' && error && <ErrorBox error={razorpayErrorMessage(error)} />}
              <div className={styles.actions}>
                <RazorpayPayButton
                  amountPaise={grandTotal}
                  disabled={busy}
                  createOrder={() => {
                    const key = crypto.randomUUID();
                    setIdempotencyKey(key);
                    return shopApi.createRazorpayOrder(
                      items.map((i) => ({ productSize: i.productSizeId, quantity: i.quantity })),
                      key,
                      appliedCoupon,
                    );
                  }}
                  onVerified={onRazorpayVerified}
                  onCancelled={onRazorpayCancelled}
                  onError={onRazorpayError}
                />
                <button type="button" className={`${styles.button} ${styles.buttonSecondary}`} onClick={() => setAtPayment(false)} disabled={busy}>
                  Back to Cart
                </button>
              </div>
            </>
          ) : (
            <>
              <TestPayment outcome={testOutcome} onChange={setTestOutcome} disabled={busy} />

              {phase === 'error' && error && <ErrorBox error={error} onRetry={isRetryablePaymentError(error) ? retry : undefined} />}

              <div className={styles.actions}>
                <button type="button" className={styles.button} onClick={onPay} disabled={busy}>
                  {busy ? <Spinner size={16} label="Processing" /> : 'Pay (Test Mode)'}
                </button>
                <button type="button" className={`${styles.button} ${styles.buttonSecondary}`} onClick={() => setAtPayment(false)} disabled={busy}>
                  Back to Cart
                </button>
              </div>
            </>
          )}
        </Panel>
      </PageShell>
    );
  }

  return (
    <PageShell title="Cart" background="dotted">
      <div className={styles.list}>
        {items.map((item) => (
          <Panel key={item.productSizeId} accent={accentVarForFeature('shop')}>
            <div className={styles.line}>
              <div>
                <h3 className={styles.lineName}>
                  {item.productName} — {item.sizeLabel}
                </h3>
                <span className={styles.lineMeta}>
                  <Money paise={item.unitPriceEstimate} /> each (estimate)
                </span>
              </div>
              <div className={styles.lineControls}>
                <button type="button" className={styles.qtyButton} onClick={() => updateQuantity(item.productSizeId, item.quantity - 1)}>
                  −
                </button>
                <span>{item.quantity}</span>
                <button
                  type="button"
                  className={styles.qtyButton}
                  onClick={() => updateQuantity(item.productSizeId, item.quantity + 1)}
                  disabled={item.quantity >= MAX_PER_ITEM}
                  title={item.quantity >= MAX_PER_ITEM ? LIMIT_REACHED_MESSAGE : undefined}
                >
                  +
                </button>
                <button type="button" className={styles.removeButton} onClick={() => removeItem(item.productSizeId)}>
                  Remove
                </button>
              </div>
            </div>
          </Panel>
        ))}
      </div>

      <Panel className={styles.summary}>
        <TextInput
          label="Coupon code"
          placeholder="e.g. MERCH20"
          value={couponCode}
          onChange={(e) => setCouponCode(e.target.value.toUpperCase())}
        />
        {couponChecking && <Spinner size={14} label="Checking coupon" />}
        {!couponChecking && couponResult && (
          <p className={couponResult.valid ? styles.couponValid : styles.couponInvalid}>
            {couponResult.valid ? `${couponCode.trim().toUpperCase()} applied: -₹${(couponResult.discount / 100).toFixed(2)}` : couponResult.message}
          </p>
        )}

        <OrderSummaryBreakdown breakdown={breakdown} couponCode={appliedCoupon} couponDiscount={couponDiscount} total={grandTotal} />
        <p className={styles.estimateNote}>Collect from: {pickupLocations.join(' · ')}</p>
        <p className={styles.estimateNote}>Final subtotal, discount and total are decided by the server when you pay.</p>
        <p className={styles.estimateNote}>
          Limit {MAX_PER_ITEM} per item.
          {items.some((i) => i.quantity >= MAX_PER_ITEM) ? ` ${LIMIT_REACHED_MESSAGE.replace('this item', 'at least one item')}` : ''}
        </p>

        {/* A sold-out or unavailable item sends the buyer back here to fix the cart. */}
        {phase === 'error' && error && !isRetryablePaymentError(error) && <ErrorBox error={error} />}

        <div className={styles.actions}>
          <button type="button" className={styles.button} onClick={goToPayment}>
            Proceed to Payment
          </button>
          <Link to="/shop" className={`${styles.button} ${styles.buttonSecondary}`} style={{ textDecoration: 'none' }}>
            Continue Shopping
          </Link>
        </div>
      </Panel>

    </PageShell>
  );
}

function OrderSummaryBreakdown({
  breakdown,
  couponCode,
  couponDiscount,
  total,
}: {
  breakdown: { baseSubtotal: number; saleDiscount: number; memberDiscount: number };
  couponCode: string | undefined;
  couponDiscount: number;
  total: number;
}) {
  return (
    <div className={styles.breakdown}>
      <div className={styles.summaryRow}>
        <span>Subtotal</span>
        <Money paise={breakdown.baseSubtotal} />
      </div>
      {breakdown.saleDiscount > 0 && (
        <div className={styles.summaryRow}>
          <span>Sale</span>
          <span>
            −<Money paise={breakdown.saleDiscount} />
          </span>
        </div>
      )}
      {breakdown.memberDiscount > 0 && (
        <div className={styles.summaryRow}>
          <span>Member discount</span>
          <span>
            −<Money paise={breakdown.memberDiscount} />
          </span>
        </div>
      )}
      {couponCode && couponDiscount > 0 && (
        <div className={styles.summaryRow}>
          <span>Coupon ({couponCode})</span>
          <span>
            −<Money paise={couponDiscount} />
          </span>
        </div>
      )}
      <div className={`${styles.summaryRow} ${styles.summaryTotal}`}>
        <strong>Total</strong>
        <strong>
          <Money paise={total} />
        </strong>
      </div>
    </div>
  );
}
