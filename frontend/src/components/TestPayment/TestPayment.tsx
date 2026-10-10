import styles from './TestPayment.module.scss';
import type { PaymentTestOutcome } from './paymentErrors';

const OUTCOMES: { value: PaymentTestOutcome; title: string; detail: string }[] = [
  { value: 'success', title: 'Approve', detail: 'The payment goes through.' },
  { value: 'failure', title: 'Decline', detail: 'The gateway refuses it. Nothing is charged.' },
  { value: 'pending', title: 'Leave pending', detail: 'The gateway has not answered yet. Nothing is delivered.' },
];

interface TestPaymentProps {
  outcome: PaymentTestOutcome;
  onChange: (outcome: PaymentTestOutcome) => void;
  disabled?: boolean;
}

/** The "card form" of this app. Campus League has no real payment gateway:
 * every purchase goes through the backend's mock gateway, and this panel is
 * where the buyer picks what that gateway should answer. It is shown on
 * every payment screen, in mock mode and against the real backend alike,
 * and says plainly that no money moves. */
export function TestPayment({ outcome, onChange, disabled }: TestPaymentProps) {
  return (
    <fieldset className={styles.box} disabled={disabled}>
      <legend className={styles.legend}>Test mode</legend>
      <p className={styles.note}>
        This is a demo payment screen. <strong>No real money moves and no card is needed.</strong> Choose what the test payment gateway should
        do, then pay.
      </p>
      <div className={styles.options} role="radiogroup" aria-label="Test payment result">
        {OUTCOMES.map((option) => (
          <label key={option.value} className={`${styles.option} ${outcome === option.value ? styles.optionSelected : ''}`}>
            <input
              type="radio"
              name="test-payment-outcome"
              value={option.value}
              checked={outcome === option.value}
              onChange={() => onChange(option.value)}
              className={styles.radio}
            />
            <span className={styles.optionTitle}>{option.title}</span>
            <span className={styles.optionDetail}>{option.detail}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

/** Shown on a success screen when the server answered 200 instead of 201:
 * the same Idempotency-Key had already paid, so this is the earlier result. */
export function ReplayNote() {
  return (
    <p className={styles.replay} role="status">
      This payment had already gone through, so you were not charged again. Showing the original order.
    </p>
  );
}
