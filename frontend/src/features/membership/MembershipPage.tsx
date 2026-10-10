import { useState } from 'react';
import { Link } from 'react-router-dom';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { EmptyState } from '../../components/EmptyState/EmptyState';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { Money } from '../../components/Money/Money';
import { SelectInput } from '../../components/FormField/SelectInput';
import type { ApiError } from '../../api/client';
import { useAsync } from '../../core/hooks/useAsync';
import { accentVarForFeature } from '../../core/config/accents';
import { membershipApi } from './api';
import { env } from '../../core/config/env';
import { formatDate, daysUntil } from './dates';
import type { PaymentTestOutcome, Plan, PurchaseResult } from './types';
import styles from './MembershipPage.module.scss';

const RENEWAL_WINDOW_DAYS = 30;
const TEST_OUTCOMES: { value: PaymentTestOutcome; label: string }[] = [
  { value: 'success', label: 'Success' },
  { value: 'failure', label: 'Failure' },
  { value: 'pending', label: 'Pending' },
];

type CheckoutPhase = 'idle' | 'submitting' | 'success' | 'pending' | 'error';

export function MembershipPage() {
  const plansState = useAsync(() => membershipApi.listPlans(), []);
  const myMembership = useAsync(() => membershipApi.getMyMembership(), []);

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
          ) : (
            <>
              <div className={styles.checkoutRow}>
                <span>
                  {status === 'active' || status === 'lapsed' ? 'Renew' : 'Buy'} {selectedPlan.name}
                </span>
                <Money paise={selectedPlan.price} />
              </div>

              {phase === 'error' && error && <ErrorBox error={error} onRetry={retry} />}

              {env.useMockApi && (
                <div className={styles.testOutcome}>
                  <SelectInput
                    label="Mock payment outcome"
                    hint="Dev-only control — picks what the mock gateway returns."
                    value={testOutcome}
                    onChange={(e) => setTestOutcome(e.target.value as PaymentTestOutcome)}
                    options={TEST_OUTCOMES.map((o) => ({ value: o.value, label: o.label }))}
                  />
                </div>
              )}

              <div className={styles.checkoutActions}>
                <button type="button" className={styles.button} onClick={() => void confirmPurchase()} disabled={phase === 'submitting'}>
                  {phase === 'submitting' ? <Spinner size={16} label="Processing" /> : 'Confirm Payment'}
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
        </Panel>
      )}
    </PageShell>
  );
}
