import { useState } from 'react';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { Money } from '../../components/Money/Money';
import { useAsync } from '../../core/hooks/useAsync';
import { financeApi } from './api';
import styles from './ReconcileBadge.module.scss';

/** Compares ledger totals with the same figures recomputed from source
 * records; green when every check agrees, red with an expandable list of
 * which checks disagree otherwise. */
export function ReconcileBadge() {
  const [expanded, setExpanded] = useState(false);
  const { status, data, error, reload } = useAsync(() => financeApi.reconcile(), []);

  if (status === 'loading') return <Spinner label="Checking books…" />;
  if (status === 'error') return <ErrorBox error={error!} onRetry={reload} />;
  if (!data) return null;

  return (
    <div>
      <div className={styles.row}>
        <span className={`${styles.badge} ${data.ok ? styles.ok : styles.failing}`}>{data.ok ? 'Books reconcile' : `${data.checks.filter((c) => !c.ok).length} check(s) failing`}</span>
        {!data.ok && (
          <button type="button" className={styles.toggleButton} onClick={() => setExpanded((v) => !v)}>
            {expanded ? 'Hide Checks' : 'Show Checks'}
          </button>
        )}
        <button type="button" className={styles.refreshButton} onClick={reload}>
          Refresh
        </button>
      </div>

      {!data.ok && expanded && (
        <ul className={styles.checksList}>
          {data.checks.map((check) => (
            <li key={check.name} className={`${styles.checkRow} ${check.ok ? '' : styles.checkFailing}`}>
              <span className={styles.checkName}>
                {check.ok ? '✓' : '✗'} {check.name}
              </span>
              {!check.ok && (
                <span className={styles.checkNumbers}>
                  expected <Money paise={check.expected} />, got <Money paise={check.actual} />
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
