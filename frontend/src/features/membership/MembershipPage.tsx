import { useState } from 'react';
import { Link } from 'react-router-dom';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { EmptyState } from '../../components/EmptyState/EmptyState';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { Money } from '../../components/Money/Money';
import { QRCode } from '../../components/QRCode/QRCode';
import { ReplayNote, TestPayment } from '../../components/TestPayment/TestPayment';
import { isRetryablePaymentError } from '../../components/TestPayment/paymentErrors';
import { RazorpayPayButton } from '../../components/RazorpayPayButton/RazorpayPayButton';
import type { ApiError } from '../../api/client';
import { useAsync } from '../../core/hooks/useAsync';
import { usePaymentsConfig } from '../../core/hooks/usePaymentsConfig';
import { accentVarForFeature } from '../../core/config/accents';
import { membershipApi } from './api';
import { razorpayErrorMessage } from '../payments/errors';
import type { RazorpayVerifyFields } from '../payments/types';
import { formatDate, daysUntil } from './dates';
import type { PaymentTestOutcome, Plan, PurchaseResult } from './types';
import styles from './MembershipPage.module.scss';

const RENEWAL_WINDOW_DAYS = 30;

type CheckoutPhase = 'idle' | 'submitting' | 'success' | 'pending' | 'error' | 'cancelled';

export function MembershipPage() {
  const plansState = useAsync(() => membershipApi.listPlans(), []);
  const myMembership = useAsync(() => membershipApi.getMyMembership(), []);
  const { gateway } = usePaymentsConfig();

  const [selectedPlan, setSelectedPlan] = useState<Plan | null>(null);
  const [testOutcome, setTestOutcome] = useState<PaymentTestOutcome>('success');
  const [idempotencyKey, setIdempotencyKey] = useState<string | null>(null);
  const [phase, setPhase] = useState<CheckoutPhase>('idle');
  const [result, setResult] = useState<PurchaseResult | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  const openCheckout = (plan: Plan) => {
    setSelectedPlan(plan);
    setIdempotencyKey(crypto.randomUUID());
    setPhase('idle');
    setResult(null);
    setError(null);
  };

  const closeCheckout = () => {
    setSelectedPlan(null);
    setIdempotencyKey(null);
    setPhase('idle');
  };

  const confirmPurchase = async () => {
    if (!selectedPlan || !idempotencyKey) return;
    setPhase('submitting');
    setError(null);
    try {
      const purchaseResult = await membershipApi.purchase({ plan: selectedPlan.id, testOutcome }, idempotencyKey);
      setResult(purchaseResult);
      if (purchaseResult.order.status === 'pending') {
        setPhase('pending');
      } else {
        setPhase('success');
        myMembership.reload();
      }
    } catch (err) {
      setPhase('error');
      setError(err as ApiError);
    }
  };

  const retry = () => void confirmPurchase();

  const onRazorpayVerified = async (orderId: number, fields: RazorpayVerifyFields) => {
    setPhase('submitting');
    setError(null);
    try {
      const purchaseResult = await membershipApi.verifyRazorpayPayment(orderId, fields);
      setResult(purchaseResult);
      setPhase('success');
      myMembership.reload();
    } catch (err) {
      setPhase('error');
      setError(err as ApiError);
    }
  };

  const onRazorpayCancelled = (orderId: number) => {
    void membershipApi.cancelRazorpayPayment(orderId);
    setPhase('cancelled');
  };

  const onRazorpayError = (err: ApiError) => {
    setPhase('error');
    setError(err);
  };

  const status = myMembership.data?.status;
  const current = myMembership.data?.membership;
  const showRenewalPrompt =
    status === 'lapsed' || (status === 'active' && current && daysUntil(current.endDate) <= RENEWAL_WINDOW_DAYS);

  return (
    <PageShell title="Membership" background="dotted">
      {myMembership.status === 'loading' && <Spinner fullPage label="Loading your membership…" />}
      {myMembership.status === 'error' && <ErrorBox error={myMembership.error!} onRetry={myMembership.reload} />}

      {myMembership.status === 'success' && (
        <div className={styles.statusBar}>
          <p className={styles.statusText}>
            {status === 'active' && current && (
              <>
                You're on the <strong>{current.plan.name}</strong> plan, active until {formatDate(current.endDate)}.
              </>
            )}
            {status === 'lapsed' && current && <>Your {current.plan.name} membership lapsed on {formatDate(current.endDate)}.</>}
            {status === 'none' && <>You don't have a membership yet — pick a plan below.</>}
          </p>
          {status === 'active' && (
            <Link to="/membership/card" className={`${styles.button}`} style={{ textDecoration: 'none' }}>
              View Member Card
            </Link>
          )}
        </div>
      )}

      {myMembership.status === 'success' && (
        <Panel accent={accentVarForFeature('membership')} className={styles.cardPanel}>
          {myMembership.data.memberQrToken ? (
            <>
              <QRCode value={myMembership.data.memberQrToken} size={150} />
              <div>
                <h3 className={styles.cardTitle}>Your member card</h3>
                <p className={styles.cardText}>
                  Show this code at the door and staff can confirm your membership.
                  {status === 'lapsed' && ' Your membership has lapsed, so it currently scans as "not a member".'}
                </p>
                <Link to="/membership/card" className={styles.button} style={{ textDecoration: 'none', display: 'inline-block' }}>
                  Open Full Card
                </Link>
              </div>
            </>
          ) : (
            <div>
              <h3 className={styles.cardTitle}>Join to get your card</h3>
              <p className={styles.cardText}>Buy a plan below and your member card, with its QR code for the door, appears here.</p>
            </div>
          )}
        </Panel>
      )}

      {showRenewalPrompt && current && (
        <Panel accent="var(--cl-coral)" style={{ marginBottom: '1.5rem' }}>
          <strong>{status === 'lapsed' ? 'Your membership has lapsed.' : 'Your membership is expiring soon.'}</strong>{' '}
          Renew your {current.plan.name} plan below to keep your benefits.
        </Panel>
      )}

      {plansState.status === 'loading' && <Spinner fullPage label="Loading plans…" />}
      {plansState.status === 'error' && <ErrorBox error={plansState.error!} onRetry={plansState.reload} />}
      {plansState.status === 'success' && plansState.data.length === 0 && (
        <Panel>
          <EmptyState icon="chest" title="No plans available" message="Check back once plans are published." />
        </Panel>
      )}

      {plansState.status === 'success' && plansState.data.length > 0 && (
        <div className={styles.grid}>
          {plansState.data.map((plan) => (
            <Panel key={plan.id} accent={accentVarForFeature('membership')}>
              <h3 className={styles.planName}>{plan.name}</h3>
              <p className={styles.planPrice}>
                <Money paise={plan.price} />
              </p>
              <p className={styles.planDuration}>{plan.durationMonths}-month membership</p>
              <ul className={styles.benefits}>
                <li>{plan.ticketDiscountPct}% off event tickets</li>
                <li>{plan.merchDiscountPct}% off merch</li>
              </ul>
              <button type="button" className={`${styles.button} ${styles.planButton}`} onClick={() => openCheckout(plan)}>
                {status === 'active' || status === 'lapsed' ? 'Renew' : 'Buy'}
              </button>
            </Panel>
          ))}
        </div>
      )}

      {selectedPlan && (
        <Panel accent="var(--cl-gold)" className={styles.checkout}>
          {phase === 'success' && result?.membership ? (
            <div className={styles.successBox}>
              <p>
                <strong>Payment successful!</strong> You're now covered through {formatDate(result.membership.endDate)}.
              </p>
              {result.replayed && <ReplayNote />}
              <Link to="/membership/card" className={styles.button} style={{ textDecoration: 'none', display: 'inline-block' }}>
                View Member Card
              </Link>
            </div>
          ) : phase === 'pending' ? (
            <div className={styles.successBox}>
              <p>
                <strong>Payment pending.</strong> We'll update your membership once it clears. You can check back on this page.
              </p>
              <button type="button" className={`${styles.button} ${styles.buttonSecondary}`} onClick={closeCheckout}>
                Close
              </button>
            </div>
          ) : phase === 'cancelled' ? (
            <div className={styles.successBox}>
              <p>
                <strong>Payment cancelled.</strong> Nothing was charged.
              </p>
              <button type="button" className={`${styles.button} ${styles.buttonSecondary}`} onClick={closeCheckout}>
                Close
              </button>
            </div>
          ) : (
            <>
              <div className={styles.checkoutRow}>
                <span>
                  {status === 'active' || status === 'lapsed' ? 'Renew' : 'Buy'} {selectedPlan.name}
                </span>
                <Money paise={selectedPlan.price} />
              </div>

              {gateway === 'razorpay' ? (
                <>
                  {phase === 'error' && error && <ErrorBox error={razorpayErrorMessage(error)} />}
                  <div className={styles.checkoutActions}>
                    <RazorpayPayButton
                      amountPaise={selectedPlan.price}
                      disabled={phase === 'submitting'}
                      createOrder={() => membershipApi.createRazorpayOrder(selectedPlan.id, idempotencyKey!)}
                      onVerified={onRazorpayVerified}
                      onCancelled={onRazorpayCancelled}
                      onError={onRazorpayError}
                    />
                    <button
                      type="button"
                      className={`${styles.button} ${styles.buttonSecondary}`}
                      onClick={closeCheckout}
                      disabled={phase === 'submitting'}
                    >
                      Cancel
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <TestPayment outcome={testOutcome} onChange={setTestOutcome} disabled={phase === 'submitting'} />

                  {phase === 'error' && error && <ErrorBox error={error} onRetry={isRetryablePaymentError(error) ? retry : undefined} />}

                  <div className={styles.checkoutActions}>
                    <button type="button" className={styles.button} onClick={() => void confirmPurchase()} disabled={phase === 'submitting'}>
                      {phase === 'submitting' ? <Spinner size={16} label="Processing" /> : 'Pay (Test Mode)'}
                    </button>
                    <button
                      type="button"
                      className={`${styles.button} ${styles.buttonSecondary}`}
                      onClick={closeCheckout}
                      disabled={phase === 'submitting'}
                    >
                      Cancel
                    </button>
                  </div>
                </>
              )}
            </>
          )}
        </Panel>
      )}
    </PageShell>
  );
}
