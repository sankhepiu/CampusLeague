import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { EmptyState } from '../../components/EmptyState/EmptyState';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { Money } from '../../components/Money/Money';
import { SelectInput } from '../../components/FormField/SelectInput';
import type { ApiError } from '../../api/client';
import { useAuth } from '../../core/hooks/useAuth';
import { useCart } from '../../core/hooks/useCart';
import { env } from '../../core/config/env';
import { accentVarForFeature } from '../../core/config/accents';
import { shopApi } from './api';
import type { PaymentTestOutcome, PlaceOrderResult } from './types';
import styles from './CartPage.module.scss';

type CheckoutPhase = 'idle' | 'submitting' | 'success' | 'pending' | 'error';

const TEST_OUTCOMES: { value: PaymentTestOutcome; label: string }[] = [
  { value: 'success', label: 'Success' },
  { value: 'failure', label: 'Failure' },
  { value: 'pending', label: 'Pending' },
];

export function CartPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { items, updateQuantity, removeItem, clear, estimatedSubtotal } = useCart();

  const [testOutcome, setTestOutcome] = useState<PaymentTestOutcome>('success');
  const [idempotencyKey, setIdempotencyKey] = useState<string | null>(null);
  const [phase, setPhase] = useState<CheckoutPhase>('idle');
  const [error, setError] = useState<ApiError | null>(null);
  const [result, setResult] = useState<PlaceOrderResult | null>(null);

  const checkout = async (key: string) => {
    setPhase('submitting');
    setError(null);
    try {
      const res = await shopApi.placeOrder(
        { items: items.map((i) => ({ productSize: i.productSizeId, quantity: i.quantity })), testOutcome },
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
  const onPay = () => {
    if (!user) {
      navigate('/login', { state: { from: '/shop/cart' } });
      return;
    }
    const key = crypto.randomUUID();
    setIdempotencyKey(key);
    void checkout(key);
  };

  const retry = () => {
    if (idempotencyKey) void checkout(idempotencyKey);
  };

  if (phase === 'success' && result) {
    return (
      <PageShell title="Cart" background="dotted">
        <Panel accent="var(--cl-green)" className={styles.successBox}>
          <p>
            <strong>Payment successful!</strong>
          </p>
          <p>
            Subtotal <Money paise={result.order.subtotal} /> · Discount <Money paise={result.order.discount} /> · Total{' '}
            <Money paise={result.order.total} />
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
                  disabled={item.quantity >= 10}
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
        <div className={styles.summaryRow}>
          <span>Estimated subtotal</span>
          <Money paise={estimatedSubtotal} />
        </div>
        <p className={styles.estimateNote}>Final subtotal, discount and total are decided by the server when you pay.</p>

        {phase === 'error' && error && <ErrorBox error={error} onRetry={error.code === 'payment_failed' ? retry : undefined} />}

        {env.useMockApi && (
          <div className={styles.testOutcome}>
            <SelectInput
              label="Mock payment outcome"
              hint="Dev-only control — picks what the mock gateway returns."
              value={testOutcome}
              onChange={(e) => setTestOutcome(e.target.value as PaymentTestOutcome)}
              options={TEST_OUTCOMES}
            />
          </div>
        )}

        <div className={styles.actions}>
          <button type="button" className={styles.button} onClick={onPay} disabled={phase === 'submitting'}>
            {phase === 'submitting' ? <Spinner size={16} label="Processing" /> : 'Pay'}
          </button>
          <Link to="/shop" className={`${styles.button} ${styles.buttonSecondary}`} style={{ textDecoration: 'none' }}>
            Continue Shopping
          </Link>
        </div>
      </Panel>

      {phase === 'pending' && (
        <Panel accent="var(--cl-gold)">
          <p>
            <strong>Payment pending.</strong> No stock is held yet — we'll confirm once it clears.
          </p>
        </Panel>
      )}
    </PageShell>
  );
}
