import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { Money } from '../../components/Money/Money';
import { StatusBadge } from '../../components/StatusBadge/StatusBadge';
import { ProgressBar } from '../../components/ProgressBar/ProgressBar';
import { QRCode } from '../../components/QRCode/QRCode';
import { ReplayNote, TestPayment } from '../../components/TestPayment/TestPayment';
import { isRetryablePaymentError } from '../../components/TestPayment/paymentErrors';
import { RazorpayPayButton } from '../../components/RazorpayPayButton/RazorpayPayButton';
import { PnlCard } from '../../components/PnlCard/PnlCard';
import type { ApiError } from '../../api/client';
import { useAsync } from '../../core/hooks/useAsync';
import { useAuth } from '../../core/hooks/useAuth';
import { usePaymentsConfig } from '../../core/hooks/usePaymentsConfig';
import { accentVarForFeature } from '../../core/config/accents';
import { formatDateTime } from '../../core/utils/formatDateTime';
import { eventsApi } from './api';
import { ticketsApi } from '../tickets/api';
import { CouponField } from '../coupons/CouponField';
import { useCoupon } from '../coupons/useCoupon';
import { razorpayErrorMessage } from '../payments/errors';
import type { RazorpayVerifyFields } from '../payments/types';
import type { PaymentTestOutcome, PurchaseTicketsResult } from '../tickets/types';
import type { Tier } from './types';
import styles from './EventDetailPage.module.scss';

type CheckoutPhase = 'idle' | 'submitting' | 'success' | 'pending' | 'error' | 'cancelled';

function tierAvailability(tier: Tier): { available: boolean; reason?: string } {
  if (tier.seatsLeft === 0) return { available: false, reason: 'Sold out' };
  if (!tier.saleOpen) {
    const now = Date.now();
    if (tier.saleOpens && now < new Date(tier.saleOpens).getTime()) return { available: false, reason: 'Sale not open' };
    return { available: false, reason: 'Sale closed' };
  }
  return { available: true };
}

export function EventDetailPage() {
  const { id } = useParams<{ id: string }>();
  const eventId = Number(id);
  const navigate = useNavigate();
  const { user, hasRole } = useAuth();
  const { gateway } = usePaymentsConfig();

  const { status, data: event, error, reload } = useAsync(() => eventsApi.get(eventId), [eventId]);

  const [selectedTier, setSelectedTier] = useState<Tier | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [testOutcome, setTestOutcome] = useState<PaymentTestOutcome>('success');
  const [idempotencyKey, setIdempotencyKey] = useState<string | null>(null);
  const [phase, setPhase] = useState<CheckoutPhase>('idle');
  const [purchaseError, setPurchaseError] = useState<ApiError | null>(null);
  const [purchaseResult, setPurchaseResult] = useState<PurchaseTicketsResult | null>(null);

  const [showStaffData, setShowStaffData] = useState(false);
  const canManage = hasRole('president', 'event_manager');
  const canSeeFinance = hasRole('president', 'event_manager', 'treasurer');

  const attendance = useAsync(() => eventsApi.attendance(eventId), [eventId], { enabled: canSeeFinance && showStaffData });
  const pnl = useAsync(() => eventsApi.pnl(eventId), [eventId], { enabled: canSeeFinance && showStaffData });

  // Re-checked when the quantity changes: a coupon may need a minimum order.
  const coupon = useCoupon('tickets', (selectedTier?.price ?? 0) * quantity);

  const openCheckout = (tier: Tier) => {
    if (!user) {
      navigate('/login', { state: { from: `/events/${eventId}` } });
      return;
    }
    setSelectedTier(tier);
    setQuantity(1);
    setIdempotencyKey(crypto.randomUUID());
    setPhase('idle');
    setPurchaseError(null);
    setPurchaseResult(null);
  };

  const closeCheckout = () => {
    setSelectedTier(null);
    setIdempotencyKey(null);
    setPhase('idle');
  };

  const confirmPurchase = async () => {
    if (!selectedTier || !idempotencyKey) return;
    setPhase('submitting');
    setPurchaseError(null);
    try {
      const result = await ticketsApi.purchase(eventId, { tier: selectedTier.id, quantity, testOutcome, coupon: coupon.applied }, idempotencyKey);
      setPurchaseResult(result);
      if (result.order.status === 'pending') {
        setPhase('pending');
      } else {
        setPhase('success');
        reload(); // seats_left changed
      }
    } catch (err) {
      const apiError = err as ApiError;
      setPurchaseError(apiError);
      setPhase('error');
      if (apiError.code === 'sold_out') reload(); // refresh seats_left per the brief
    }
  };

  const onRazorpayVerified = async (orderId: number, fields: RazorpayVerifyFields) => {
    setPhase('submitting');
    setPurchaseError(null);
    try {
      const result = await ticketsApi.verifyRazorpayPayment(orderId, fields);
      setPurchaseResult(result);
      setPhase('success');
      reload();
    } catch (err) {
      const apiError = err as ApiError;
      setPurchaseError(apiError);
      setPhase('error');
      if (apiError.code === 'sold_out') reload();
    }
  };

  const onRazorpayCancelled = (orderId: number) => {
    void ticketsApi.cancelRazorpayPayment(orderId);
    setPhase('cancelled');
  };

  const onRazorpayError = (err: ApiError) => {
    setPurchaseError(err);
    setPhase('error');
  };

  if (status === 'loading') return <Spinner fullPage label="Loading event…" />;
  if (status === 'error') return <ErrorBox error={error!} onRetry={reload} />;
  if (!event) return null;

  return (
    <PageShell title={event.title}>
      <div className={styles.header}>
        <div>
          <p className={styles.meta}>{formatDateTime(event.startsAt)}</p>
          <p className={styles.meta}>{event.venue}</p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <StatusBadge variant={event.status === 'on_sale' ? 'success' : event.status === 'draft' ? 'warning' : 'neutral'}>
            {event.status.replace('_', ' ')}
          </StatusBadge>
          {canManage && (
            <Link to={`/events/${event.id}/edit`} className={styles.editLink}>
              Edit Event
            </Link>
          )}
        </div>
      </div>

      <p className={styles.meta}>Organised by {event.organiser.name}</p>

      {event.description && <p className={styles.description}>{event.description}</p>}

      <Panel accent={accentVarForFeature('events')} className={styles.capacityPanel}>
        <ProgressBar
          percent={event.capacity > 0 ? (event.sold / event.capacity) * 100 : 0}
          label={`${event.sold} sold · ${event.seatsLeft} seat${event.seatsLeft === 1 ? '' : 's'} left · ${event.checkedIn} checked in`}
        />
      </Panel>

      <div className={styles.tierGrid}>
        {event.tiers.map((tier) => {
          const { available, reason } = tierAvailability(tier);
          const isMemberPrice = user?.membershipStatus === 'active' && tier.price === tier.memberPrice && tier.memberPrice !== tier.publicPrice;
          return (
            <Panel key={tier.id} accent={accentVarForFeature('events')}>
              <h3 className={styles.tierName}>{tier.name}</h3>
              <div className={styles.priceRow}>
                <span className={styles.price}>
                  <Money paise={tier.price} />
                </span>
                {isMemberPrice && <StatusBadge variant="info">Member price</StatusBadge>}
              </div>
              {tier.memberPrice !== tier.publicPrice && (
                <p className={styles.referencePrice}>
                  Public <Money paise={tier.publicPrice} className={isMemberPrice ? styles.strike : undefined} /> · Member{' '}
                  <Money paise={tier.memberPrice} />
                </p>
              )}
              <p className={styles.seats}>{available ? `${tier.seatsLeft} seat${tier.seatsLeft === 1 ? '' : 's'} left` : reason}</p>
              <button type="button" className={styles.tierButton} disabled={!available} onClick={() => openCheckout(tier)}>
                {available ? 'Buy' : reason}
              </button>
            </Panel>
          );
        })}
      </div>

      {selectedTier && (
        <Panel accent="var(--cl-gold)" className={styles.checkout}>
          {phase === 'success' && purchaseResult ? (
            <div className={styles.successBox}>
              <p>
                <strong>Payment successful!</strong> You bought {purchaseResult.tickets.length} ticket
                {purchaseResult.tickets.length === 1 ? '' : 's'} for {selectedTier.name}.
              </p>
              {purchaseResult.replayed && <ReplayNote />}
              {purchaseResult.pass && (
                <div style={{ display: 'flex', justifyContent: 'center', margin: '1rem 0' }}>
                  <QRCode value={purchaseResult.pass.qrToken} size={160} />
                </div>
              )}
              <ul className={styles.ticketList}>
                {purchaseResult.tickets.map((t) => (
                  <li key={t.id} className={styles.ticketRow}>
                    {t.code}
                  </li>
                ))}
              </ul>
              <Link to="/tickets" className={styles.button} style={{ textDecoration: 'none', display: 'inline-block' }}>
                View My Tickets
              </Link>
            </div>
          ) : phase === 'pending' ? (
            <div className={styles.successBox}>
              <p>
                <strong>Payment pending.</strong> No seat is held yet — we'll confirm once it clears.
              </p>
              <button type="button" className={`${styles.button} ${styles.buttonSecondary}`} onClick={closeCheckout}>
                Close
              </button>
            </div>
          ) : phase === 'cancelled' ? (
            <div className={styles.successBox}>
              <p>
                <strong>Payment cancelled.</strong> No seat was held and nothing was charged.
              </p>
              <button type="button" className={`${styles.button} ${styles.buttonSecondary}`} onClick={closeCheckout}>
                Close
              </button>
            </div>
          ) : (
            <>
              <div className={styles.checkoutRow}>
                <span>Buy {selectedTier.name}</span>
                <Money paise={selectedTier.price * quantity} />
              </div>

              <div className={styles.quantityRow}>
                <span>Quantity</span>
                <button type="button" className={styles.qtyButton} onClick={() => setQuantity((q) => Math.max(1, q - 1))} disabled={quantity <= 1}>
                  −
                </button>
                <span>{quantity}</span>
                <button
                  type="button"
                  className={styles.qtyButton}
                  onClick={() => setQuantity((q) => Math.min(10, q + 1, selectedTier.seatsLeft))}
                  disabled={quantity >= 10 || quantity >= selectedTier.seatsLeft}
                >
                  +
                </button>
              </div>

              <CouponField coupon={coupon} amount={selectedTier.price * quantity} placeholder="e.g. GALA50" disabled={phase === 'submitting'} />

              {gateway === 'razorpay' ? (
                <>
                  {phase === 'error' && purchaseError && <ErrorBox error={razorpayErrorMessage(purchaseError)} />}
                  <div className={styles.checkoutActions}>
                    <RazorpayPayButton
                      amountPaise={selectedTier.price * quantity - coupon.discount}
                      disabled={phase === 'submitting'}
                      // A new key each time the checkout is opened: the last
                      // one belongs to an order that was closed (cancelled)
                      // or priced with a different coupon or quantity, and
                      // the server refuses to reuse it.
                      createOrder={() => {
                        const key = crypto.randomUUID();
                        setIdempotencyKey(key);
                        return ticketsApi.createRazorpayOrder(eventId, selectedTier.id, quantity, key, coupon.applied);
                      }}
                      onVerified={onRazorpayVerified}
                      onCancelled={onRazorpayCancelled}
                      onError={onRazorpayError}
                    />
                    <button type="button" className={`${styles.button} ${styles.buttonSecondary}`} onClick={closeCheckout} disabled={phase === 'submitting'}>
                      Cancel
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <TestPayment outcome={testOutcome} onChange={setTestOutcome} disabled={phase === 'submitting'} />

                  {phase === 'error' && purchaseError && (
                    <ErrorBox error={purchaseError} onRetry={isRetryablePaymentError(purchaseError) ? () => void confirmPurchase() : undefined} />
                  )}

                  <div className={styles.checkoutActions}>
                    <button type="button" className={styles.button} onClick={() => void confirmPurchase()} disabled={phase === 'submitting'}>
                      {phase === 'submitting' ? <Spinner size={16} label="Processing" /> : 'Pay (Test Mode)'}
                    </button>
                    <button type="button" className={`${styles.button} ${styles.buttonSecondary}`} onClick={closeCheckout} disabled={phase === 'submitting'}>
                      Cancel
                    </button>
                  </div>
                </>
              )}
            </>
          )}
        </Panel>
      )}

      {canSeeFinance && (
        <div className={styles.staffSection}>
          <button type="button" className={styles.staffToggle} onClick={() => setShowStaffData((v) => !v)}>
            {showStaffData ? 'Hide' : 'Show'} Attendance &amp; P&amp;L
          </button>

          {showStaffData && (
            <>
              {attendance.status === 'loading' && <Spinner label="Loading attendance…" />}
              {attendance.status === 'error' && <ErrorBox error={attendance.error!} onRetry={attendance.reload} />}
              {attendance.status === 'success' && (
                <Panel accent="var(--cl-cyan)" style={{ marginBottom: '1rem' }}>
                  <h3 className={styles.tierName}>Attendance</h3>
                  <p className={styles.meta}>
                    {attendance.data.checkedIn} checked in of {attendance.data.sold} sold
                    {attendance.data.attendanceRatePct !== null && ` (${attendance.data.attendanceRatePct}%)`}
                  </p>
                </Panel>
              )}

              {pnl.status === 'loading' && <Spinner label="Loading P&L…" />}
              {pnl.status === 'error' && <ErrorBox error={pnl.error!} onRetry={pnl.reload} />}
              {pnl.status === 'success' && <PnlCard data={pnl.data} accent="var(--cl-green)" />}
            </>
          )}
        </div>
      )}
    </PageShell>
  );
}
