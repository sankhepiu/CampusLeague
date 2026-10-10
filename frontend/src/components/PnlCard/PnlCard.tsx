import { Panel } from '../Panel/Panel';
import { Money } from '../Money/Money';
import styles from './PnlCard.module.scss';

interface PnlAccountLine {
  code: string;
  name: string;
  amount: number;
}

interface PnlData {
  revenue: { total: number; byAccount: PnlAccountLine[] };
  expenses: { total: number; byAccount: PnlAccountLine[] };
  profit: number;
  budget: { amount: number; spent: number; remaining: number };
  attendance?: { sold: number; checkedIn: number; attendanceRatePct: number | null };
}

interface PnlCardProps {
  title?: string;
  data: PnlData;
  accent?: string;
  /** When given, the profit figure becomes a button that opens the Coin
   * Trail for it (finance screens only — EventDetailPage leaves this unset). */
  onProfitClick?: () => void;
}

/** Revenue/expenses/profit/budget summary. Feature-agnostic by design (takes
 * a plain data shape, not an events-specific type) so finance screens can
 * reuse it for any P&L-shaped figures. */
export function PnlCard({ title = 'Profit & Loss', data, accent, onProfitClick }: PnlCardProps) {
  return (
    <Panel accent={accent}>
      <h3 className={styles.title}>{title}</h3>

      <div className={styles.grid}>
        <div className={styles.stat}>
          <span className={styles.statLabel}>Revenue</span>
          <span className={styles.statValue}>
            <Money paise={data.revenue.total} />
          </span>
        </div>
        <div className={styles.stat}>
          <span className={styles.statLabel}>Expenses</span>
          <span className={styles.statValue}>
            <Money paise={data.expenses.total} />
          </span>
        </div>
        <div className={styles.stat}>
          <span className={styles.statLabel}>Profit</span>
          {onProfitClick ? (
            <button type="button" className={`${styles.statValue} ${styles.profitButton} ${data.profit >= 0 ? styles.positive : styles.negative}`} onClick={onProfitClick}>
              <Money paise={data.profit} />
            </button>
          ) : (
            <span className={`${styles.statValue} ${data.profit >= 0 ? styles.positive : styles.negative}`}>
              <Money paise={data.profit} />
            </span>
          )}
        </div>
      </div>

      <div className={styles.section}>
        <p className={styles.sectionLabel}>Budget</p>
        <div className={styles.grid}>
          <div className={styles.stat}>
            <span className={styles.statLabel}>Allocated</span>
            <span className={styles.statValue}>
              <Money paise={data.budget.amount} />
            </span>
          </div>
          <div className={styles.stat}>
            <span className={styles.statLabel}>Spent</span>
            <span className={styles.statValue}>
              <Money paise={data.budget.spent} />
            </span>
          </div>
          <div className={styles.stat}>
            <span className={styles.statLabel}>Remaining</span>
            <span className={`${styles.statValue} ${data.budget.remaining >= 0 ? styles.positive : styles.negative}`}>
              <Money paise={data.budget.remaining} />
            </span>
          </div>
        </div>
      </div>

      {data.revenue.byAccount.length > 0 && (
        <div className={styles.section}>
          <p className={styles.sectionLabel}>Revenue by account</p>
          <ul className={styles.accountRows}>
            {data.revenue.byAccount.map((line) => (
              <li key={line.code} className={styles.accountRow}>
                <span>{line.name}</span>
                <Money paise={line.amount} />
              </li>
            ))}
          </ul>
        </div>
      )}

      {data.expenses.byAccount.length > 0 && (
        <div className={styles.section}>
          <p className={styles.sectionLabel}>Expenses by account</p>
          <ul className={styles.accountRows}>
            {data.expenses.byAccount.map((line) => (
              <li key={line.code} className={styles.accountRow}>
                <span>{line.name}</span>
                <Money paise={line.amount} />
              </li>
            ))}
          </ul>
        </div>
      )}

      {data.attendance && (
        <div className={styles.section}>
          <p className={styles.sectionLabel}>Attendance</p>
          <p className={styles.accountRow} style={{ borderBottom: 'none' }}>
            <span>
              {data.attendance.checkedIn} checked in of {data.attendance.sold} sold
            </span>
            {data.attendance.attendanceRatePct !== null && <span>{data.attendance.attendanceRatePct}%</span>}
          </p>
        </div>
      )}
    </Panel>
  );
}
