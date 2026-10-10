import { useState } from 'react';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { EmptyState } from '../../components/EmptyState/EmptyState';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { Money } from '../../components/Money/Money';
import { StatusBadge, type StatusBadgeVariant } from '../../components/StatusBadge/StatusBadge';
import { SelectInput } from '../../components/FormField/SelectInput';
import type { ApiError } from '../../api/client';
import { useAsync } from '../../core/hooks/useAsync';
import { useAuth } from '../../core/hooks/useAuth';
import { accentVarForFeature } from '../../core/config/accents';
import { expensesApi } from './api';
import { ExpenseKanban } from './ExpenseKanban';
import type { Expense, ExpenseStatus } from './types';
import styles from './ExpenseApprovalPage.module.scss';
import { formatDateTime } from '../../core/utils/formatDateTime';

type ViewMode = 'list' | 'kanban';

const STATUS_VARIANT: Record<ExpenseStatus, StatusBadgeVariant> = { submitted: 'warning', approved: 'info', rejected: 'danger', paid: 'success' };
const CATEGORY_LABEL: Record<string, string> = { event: 'Event', fundraiser: 'Fundraiser', general: 'General' };
const FILTER_OPTIONS: { value: ExpenseStatus | ''; label: string }[] = [
  { value: 'submitted', label: 'Approval queue (submitted)' },
  { value: '', label: 'All requests' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'paid', label: 'Paid' },
];

export function ExpenseApprovalPage() {
  const { user } = useAuth();
  const [viewMode, setViewMode] = useState<ViewMode>('kanban');
  const [filter, setFilter] = useState<ExpenseStatus | ''>('submitted');
  const { status, data, error, reload } = useAsync(() => expensesApi.listAll({ status: filter || undefined }), [filter], {
    enabled: viewMode === 'list',
  });

  return (
    <PageShell title="Expense Approvals">
      <div className={styles.viewToggle} role="tablist" aria-label="Approvals view">
        <button
          type="button"
          role="tab"
          aria-selected={viewMode === 'kanban'}
          className={`${styles.toggleButton} ${viewMode === 'kanban' ? styles.toggleButtonActive : ''}`}
          onClick={() => setViewMode('kanban')}
        >
          Kanban
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={viewMode === 'list'}
          className={`${styles.toggleButton} ${viewMode === 'list' ? styles.toggleButtonActive : ''}`}
          onClick={() => setViewMode('list')}
        >
          List
        </button>
      </div>

      {viewMode === 'kanban' && <ExpenseKanban currentUserId={user?.id ?? null} />}

      {viewMode === 'list' && (
        <>
          <div className={styles.filterRow}>
            <SelectInput label="View" value={filter} onChange={(e) => setFilter(e.target.value as ExpenseStatus | '')} options={FILTER_OPTIONS} />
          </div>

          {status === 'loading' && <Spinner fullPage label="Loading requests…" />}
          {status === 'error' && <ErrorBox error={error!} onRetry={reload} />}
          {status === 'success' && data.results.length === 0 && (
            <Panel>
              <EmptyState icon="coin" title="Nothing here" message="No requests match this view." />
            </Panel>
          )}

          {status === 'success' && data.results.length > 0 && (
            <div className={styles.list}>
              {data.results.map((expense) => (
                <ExpenseRow key={expense.id} expense={expense} currentUserId={user?.id ?? null} onChanged={reload} />
              ))}
            </div>
          )}
        </>
      )}
    </PageShell>
  );
}

function ExpenseRow({ expense, currentUserId, onChanged }: { expense: Expense; currentUserId: number | null; onChanged: () => void }) {
  const isOwnRequest = currentUserId !== null && expense.requester.id === currentUserId;
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [showReject, setShowReject] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [rejectValidation, setRejectValidation] = useState<string | null>(null);

  const handleInvalidStatus = (err: ApiError) => {
    if (err.code === 'invalid_status') {
      setActionError('This request was already decided — refreshing.');
      onChanged();
    } else if (err.code === 'self_approval') {
      setActionError('You cannot decide your own request.');
    } else {
      setActionError(err.message);
    }
  };

  const approve = async () => {
    setBusy(true);
    setActionError(null);
    try {
      await expensesApi.approve(expense.id);
      onChanged();
    } catch (err) {
      handleInvalidStatus(err as ApiError);
    } finally {
      setBusy(false);
    }
  };

  const submitReject = async () => {
    if (!rejectReason.trim()) {
      setRejectValidation('A reason is required to reject a request.');
      return;
    }
    setRejectValidation(null);
    setBusy(true);
    setActionError(null);
    try {
      await expensesApi.reject(expense.id, rejectReason.trim());
      onChanged();
    } catch (err) {
      handleInvalidStatus(err as ApiError);
    } finally {
      setBusy(false);
    }
  };

  const markPaid = async () => {
    setBusy(true);
    setActionError(null);
    try {
      await expensesApi.markPaid(expense.id);
      onChanged();
    } catch (err) {
      handleInvalidStatus(err as ApiError);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel accent={accentVarForFeature('expenses')}>
      <div className={styles.row}>
        <div>
          <span className={styles.amount}>
            <Money paise={expense.amount} />
          </span>
          <p className={styles.meta}>
            {expense.requester.name} · {CATEGORY_LABEL[expense.category]} · {formatDateTime(expense.createdAt)}
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

      {actionError && <ErrorBox error={actionError} />}

      {isOwnRequest ? (
        <p className={styles.selfNote}>This is your own request — you cannot approve or reject it.</p>
      ) : (
        <>
          {expense.status === 'submitted' && (
            <div className={styles.actions}>
              <button type="button" className={styles.button} onClick={approve} disabled={busy}>
                {busy ? <Spinner size={14} label="Working" /> : 'Approve'}
              </button>
              <button type="button" className={`${styles.button} ${styles.buttonDanger}`} onClick={() => setShowReject((v) => !v)} disabled={busy}>
                Reject
              </button>
            </div>
          )}
          {showReject && expense.status === 'submitted' && (
            <div className={styles.rejectForm}>
              <textarea className={styles.textarea} placeholder="Reason for rejection (required)" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} />
              {rejectValidation && <p className={styles.error}>{rejectValidation}</p>}
              <div className={styles.actions}>
                <button type="button" className={`${styles.button} ${styles.buttonDanger}`} onClick={submitReject} disabled={busy}>
                  {busy ? <Spinner size={14} label="Working" /> : 'Confirm Reject'}
                </button>
                <button type="button" className={`${styles.button} ${styles.buttonSecondary}`} onClick={() => setShowReject(false)} disabled={busy}>
                  Cancel
                </button>
              </div>
            </div>
          )}
          {expense.status === 'approved' && (
            <div className={styles.actions}>
              <button type="button" className={styles.button} onClick={markPaid} disabled={busy}>
                {busy ? <Spinner size={14} label="Working" /> : 'Mark Paid'}
              </button>
            </div>
          )}
        </>
      )}
    </Panel>
  );
}
