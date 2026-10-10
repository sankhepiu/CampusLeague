import { Panel } from '../../components/Panel/Panel';
import { Money } from '../../components/Money/Money';
import { useCountUp } from '../../core/hooks/useCountUp';
import { accentVarForFeature } from '../../core/config/accents';
import styles from './FinanceBalance.module.scss';

const DEMO_BALANCE_PAISE = 18_47_250; // ₹18,472.50 — placeholder until real ledger data ships

/** Sample "Club Balance" stat that counts up on mount, demonstrating the
 * count-up treatment finance totals get. No 3D/tilt here by design — finance
 * surfaces stay flat even in the "premium" pass. */
export function FinanceBalance() {
  const animated = useCountUp(DEMO_BALANCE_PAISE);

  return (
    <Panel accent={accentVarForFeature('finance')} className={styles.stat}>
      <p className={styles.label}>Club Balance (sample)</p>
      <p className={styles.value}>
        <Money paise={animated} />
      </p>
    </Panel>
  );
}
