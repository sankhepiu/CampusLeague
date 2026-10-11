import { TextInput } from '../../components/FormField/TextInput';
import { Spinner } from '../../components/Spinner/Spinner';
import { Money } from '../../components/Money/Money';
import type { CouponState } from './useCoupon';
import styles from './CouponField.module.scss';

interface CouponFieldProps {
  coupon: CouponState;
  /** What the purchase costs before the coupon, in paise. */
  amount: number;
  placeholder?: string;
  disabled?: boolean;
}

export function CouponField({ coupon, amount, placeholder = 'Coupon code', disabled }: CouponFieldProps) {
  return (
    <div className={styles.field}>
      <TextInput label="Coupon code" placeholder={placeholder} value={coupon.code} onChange={(e) => coupon.setCode(e.target.value)} disabled={disabled} />
      {coupon.checking && <Spinner size={14} label="Checking coupon" />}
      {!coupon.checking && coupon.result && (
        <p className={coupon.result.valid ? styles.valid : styles.invalid}>
          {coupon.result.valid ? (
            <>
              {coupon.applied} applied: −<Money paise={coupon.discount} />
            </>
          ) : (
            coupon.result.message
          )}
        </p>
      )}
      {coupon.applied && (
        <p className={styles.total}>
          <strong>Total</strong>
          <strong>
            <Money paise={amount - coupon.discount} />
          </strong>
        </p>
      )}
    </div>
  );
}
