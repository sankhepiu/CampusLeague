import { useState } from 'react';
import { Link } from 'react-router-dom';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { EmptyState } from '../../components/EmptyState/EmptyState';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { Money } from '../../components/Money/Money';
import { StatusBadge, type StatusBadgeVariant } from '../../components/StatusBadge/StatusBadge';
import { useAsync } from '../../core/hooks/useAsync';
import { accentVarForFeature } from '../../core/config/accents';
import { expensesApi } from './api';
import type { ExpenseStatus } from './types';
import styles from './MyExpensesPage.module.scss';
import { formatDateOnly, formatDateTime } from '../../core/utils/formatDateTime';

const STATUS_VARIANT: Record<ExpenseStatus, StatusBadgeVariant> = { submitted: 'warning', approved: 'info', rejected: 'danger', paid: 'success' };
const CATEGORY_LABEL: Record<string, string> = { event: 'Event', fundraiser: 'Fundraiser', general: 'General' };

export function MyExpensesPage() {
  const [page, setPage] = useState(1);
  const { status, data, error, reload } = useAsync(() => expensesApi.listMine(page), [page]);

  return (
    <PageShell title="My Requests" background="dotted">
      <div className={styles.header}>
        <Link to="/expenses/new" className={styles.newButton}>
          + New Request
        </Link>
      </div>

      {status === 'loading' && <Spinner fullPage label="Loading your requests…" />}
      {status === 'error' && <ErrorBox error={error!} onRetry={reload} />}
      {status === 'success' && data.results.length === 0 && (
        <Panel>
          <EmptyState icon="coin" title="No requests yet" message="Submit a reimbursement request to see it here." />
        </Panel>
      )}

      {status === 'success' && data.results.length > 0 && (
        <>
          <div className={styles.list}>
            {data.results.map((expense) => (
              <Panel key={expense.id} accent={accentVarForFeature('expenses')}>
                <div className={styles.row}>
                  <div>
                    <span className={styles.amount}>
                      <Money paise={expense.amount} />
                    </span>
                    <p className={styles.meta}>
                      {CATEGORY_LABEL[expense.category]} · {formatDateTime(expense.createdAt)}
                    </p>
                    <p className={styles.meta}>{expense.description}</p>
                    {expense.receiptUrl && (
                      <a href={expense.receiptUrl} target="_blank" rel="noreferrer" className={styles.receiptLink}>
                        View Receipt
                      </a>
                    )}
                  </div>
                  <StatusBadge variant={STATUS_VARIANT[expense.status]}>{expense.status}</StatusBadge>
                </div>

                {expense.approval && (
                  <div className={styles.approvalBox}>
                    {expense.approval.decision === 'approved' ? 'Approved' : 'Rejected'} by {expense.approval.approver.name} on{' '}
                    {formatDateOnly(expense.approval.decidedAt)}
                    {expense.approval.reason && <> — {expense.approval.reason}</>}
                  </div>
                )}
              </Panel>
            ))}
          </div>

          <div className={styles.pagination}>
            <button type="button" className={styles.pageButton} onClick={() => setPage((p) => p - 1)} disabled={!data.previous}>
              ← Previous
            </button>
            <button type="button" className={styles.pageButton} onClick={() => setPage((p) => p + 1)} disabled={!data.next}>
              Next →
            </button>
          </div>
        </>
      )}
    </PageShell>
  );
}
