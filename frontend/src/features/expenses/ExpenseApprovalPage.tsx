import { useEffect, useRef, useState, type DragEvent, type FormEvent } from 'react';
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
import type { Expense, ExpenseStatus } from './types';
import styles from './ExpenseApprovalPage.module.scss';
import { formatDateOnly, formatDateTime } from '../../core/utils/formatDateTime';

const STATUS_VARIANT: Record<ExpenseStatus, StatusBadgeVariant> = { submitted: 'warning', approved: 'info', rejected: 'danger', paid: 'success' };
const CATEGORY_LABEL: Record<string, string> = { event: 'Event', fundraiser: 'Fundraiser', general: 'General' };
const FILTER_OPTIONS: { value: ExpenseStatus | ''; label: string }[] = [
  { value: 'submitted', label: 'Approval queue (submitted)' },
  { value: '', label: 'All requests' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'paid', label: 'Paid' },
];

const BOARD_COLUMNS: { status: ExpenseStatus; label: string }[] = [
  { status: 'submitted', label: 'Submitted' },
  { status: 'approved', label: 'Approved' },
  { status: 'paid', label: 'Paid' },
  { status: 'rejected', label: 'Rejected' },
];

/** The only drops the backend will accept — everything else snaps back. */
function allowedTargets(current: ExpenseStatus): ExpenseStatus[] {
  if (current === 'submitted') return ['approved', 'rejected'];
  if (current === 'approved') return ['paid'];
  return [];
}

const DRAG_MIME = 'text/plain';
const MIN_REASON = 5;

/** A rejection is a normal outcome, not a failure: a calm line, never an ErrorBox. */
function RejectionNote({ expense }: { expense: Expense }) {
  if (expense.status !== 'rejected' || !expense.approval) return null;
  const { approver, decidedAt, reason } = expense.approval;
  return (
    <p className={styles.rejectionNote}>
      Rejected by {approver.name} on {formatDateOnly(decidedAt)}{reason ? `: ${reason}` : ''}
    </p>
  );
}

export function ExpenseApprovalPage() {
  const { user } = useAuth();
  const [view, setView] = useState<'board' | 'list'>('board');
  const [filter, setFilter] = useState<ExpenseStatus | ''>('submitted');
  // Board shows every status at once (split into columns); list respects the filter dropdown.
  const { status, data, error, reload } = useAsync(() => expensesApi.listAll(view === 'list' ? { status: filter || undefined } : {}), [view, filter]);

  const [expenses, setExpenses] = useState<Expense[]>([]);
  useEffect(() => {
    if (data) setExpenses(data.results);
  }, [data]);

  return (
    <PageShell title="Expense Approvals">
      <div className={styles.viewToggle}>
        <button type="button" className={`${styles.toggleButton} ${view === 'board' ? styles.toggleButtonActive : ''}`} onClick={() => setView('board')}>
          Board
        </button>
        <button type="button" className={`${styles.toggleButton} ${view === 'list' ? styles.toggleButtonActive : ''}`} onClick={() => setView('list')}>
          List
        </button>
      </div>

      {view === 'list' && (
        <div className={styles.filterRow}>
          <SelectInput label="View" value={filter} onChange={(e) => setFilter(e.target.value as ExpenseStatus | '')} options={FILTER_OPTIONS} />
        </div>
      )}

      {status === 'loading' && <Spinner fullPage label="Loading requests…" />}
      {status === 'error' && <ErrorBox error={error!} onRetry={reload} />}

      {status === 'success' && view === 'list' && data.results.length === 0 && (
        <Panel>
          <EmptyState icon="coin" title="Nothing here" message="No requests match this view." />
        </Panel>
      )}

      {status === 'success' && view === 'list' && data.results.length > 0 && (
        <div className={styles.list}>
          {data.results.map((expense) => (
            <ExpenseRow key={expense.id} expense={expense} currentUserId={user?.id ?? null} onChanged={reload} />
          ))}
        </div>
      )}

      {status === 'success' && view === 'board' && (
        <ExpenseBoard expenses={expenses} setExpenses={setExpenses} currentUserId={user?.id ?? null} onReload={reload} />
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
    if (rejectReason.trim().length < MIN_REASON) {
      setRejectValidation(`Give a reason of at least ${MIN_REASON} characters.`);
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

      <RejectionNote expense={expense} />

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
              <textarea className={styles.textarea} placeholder="Reason for rejection (at least 5 characters)" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} />
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

interface PendingReject {
  expenseId: number;
  prevStatus: ExpenseStatus;
}

function ExpenseBoard({
  expenses,
  setExpenses,
  currentUserId,
  onReload,
}: {
  expenses: Expense[];
  setExpenses: (updater: (es: Expense[]) => Expense[]) => void;
  currentUserId: number | null;
  onReload: () => void;
}) {
  const [draggingId, setDraggingId] = useState<number | null>(null);
  const [dragOverColumn, setDragOverColumn] = useState<ExpenseStatus | null>(null);
  const [moveError, setMoveError] = useState<{ expenseId: number; message: string } | null>(null);
  const [pendingReject, setPendingReject] = useState<PendingReject | null>(null);

  const patchExpense = (id: number, patch: Partial<Expense>) => setExpenses((es) => es.map((e) => (e.id === id ? { ...e, ...patch } : e)));
  const replaceExpense = (updated: Expense) => setExpenses((es) => es.map((e) => (e.id === updated.id ? updated : e)));

  const moveExpense = (expenseId: number, nextStatus: ExpenseStatus) => {
    const expense = expenses.find((e) => e.id === expenseId);
    if (!expense || expense.status === nextStatus) return;

    if (currentUserId !== null && expense.requester.id === currentUserId) {
      setMoveError({ expenseId, message: "This is your own request — it needs another approver." });
      return;
    }

    if (!allowedTargets(expense.status).includes(nextStatus)) {
      setMoveError({ expenseId, message: "That move isn't allowed." });
      return;
    }

    setMoveError(null);

    if (nextStatus === 'rejected') {
      setPendingReject({ expenseId, prevStatus: expense.status });
      return;
    }

    const prevStatus = expense.status;
    patchExpense(expenseId, { status: nextStatus });
    const action = nextStatus === 'approved' ? expensesApi.approve(expenseId) : expensesApi.markPaid(expenseId);
    action
      .then(replaceExpense)
      .catch((err: ApiError) => {
        patchExpense(expenseId, { status: prevStatus });
        if (err.code === 'invalid_status') {
          setMoveError({ expenseId, message: 'This request was already decided — refreshing.' });
          onReload();
        } else {
          setMoveError({ expenseId, message: err.message });
        }
      });
  };

  const confirmReject = async (reason: string) => {
    if (!pendingReject) return;
    const { expenseId, prevStatus } = pendingReject;
    setPendingReject(null);
    patchExpense(expenseId, { status: 'rejected' });
    try {
      const updated = await expensesApi.reject(expenseId, reason);
      replaceExpense(updated);
    } catch (err) {
      patchExpense(expenseId, { status: prevStatus });
      const apiErr = err as ApiError;
      if (apiErr.code === 'invalid_status') {
        setMoveError({ expenseId, message: 'This request was already decided — refreshing.' });
        onReload();
      } else {
        setMoveError({ expenseId, message: apiErr.message });
      }
    }
  };

  const rejectingExpense = pendingReject ? expenses.find((e) => e.id === pendingReject.expenseId) ?? null : null;

  return (
    <>
      <div className={styles.columns}>
        {BOARD_COLUMNS.map((col) => {
          const colExpenses = expenses.filter((e) => e.status === col.status);
          return (
            <div
              key={col.status}
              className={`${styles.column} ${dragOverColumn === col.status ? styles.columnDragOver : ''}`}
              onDragOver={(e: DragEvent<HTMLDivElement>) => {
                if (draggingId === null) return;
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                setDragOverColumn(col.status);
              }}
              onDragLeave={(e: DragEvent<HTMLDivElement>) => {
                if (e.currentTarget.contains(e.relatedTarget as Node | null)) return;
                setDragOverColumn((cur) => (cur === col.status ? null : cur));
              }}
              onDrop={(e: DragEvent<HTMLDivElement>) => {
                e.preventDefault();
                setDragOverColumn(null);
                const expenseId = Number(e.dataTransfer.getData(DRAG_MIME));
                if (Number.isFinite(expenseId)) moveExpense(expenseId, col.status);
              }}
            >
              <h3 className={styles.columnTitle}>
                {col.label} <span className={styles.columnCount}>({colExpenses.length})</span>
              </h3>
              {colExpenses.map((expense) => (
                <ExpenseCard
                  key={expense.id}
                  expense={expense}
                  isOwnRequest={currentUserId !== null && expense.requester.id === currentUserId}
                  moveError={moveError?.expenseId === expense.id ? moveError.message : null}
                  onMove={moveExpense}
                  onDragStart={() => setDraggingId(expense.id)}
                  onDragEnd={() => {
                    setDraggingId(null);
                    setDragOverColumn(null);
                  }}
                />
              ))}
              {colExpenses.length === 0 && <p className={styles.meta}>Nothing here.</p>}
            </div>
          );
        })}
      </div>

      <RejectReasonModal
        open={pendingReject !== null}
        amount={rejectingExpense?.amount ?? 0}
        onCancel={() => setPendingReject(null)}
        onConfirm={confirmReject}
      />
    </>
  );
}

function ExpenseCard({
  expense,
  isOwnRequest,
  moveError,
  onMove,
  onDragStart,
  onDragEnd,
}: {
  expense: Expense;
  isOwnRequest: boolean;
  moveError: string | null;
  onMove: (expenseId: number, next: ExpenseStatus) => void;
  onDragStart: () => void;
  onDragEnd: () => void;
}) {
  const [showMoveMenu, setShowMoveMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const canDrag = !isOwnRequest;
  const targets = allowedTargets(expense.status);

  useEffect(() => {
    if (!showMoveMenu) return;
    const onClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setShowMoveMenu(false);
    };
    document.addEventListener('click', onClickOutside);
    return () => document.removeEventListener('click', onClickOutside);
  }, [showMoveMenu]);

  return (
    <Panel
      className={styles.expenseCard}
      accent={accentVarForFeature('expenses')}
      draggable={canDrag}
      onDragStart={(e: DragEvent<HTMLDivElement>) => {
        e.dataTransfer.setData(DRAG_MIME, String(expense.id));
        e.dataTransfer.effectAllowed = 'move';
        onDragStart();
      }}
      onDragEnd={onDragEnd}
    >
      <div className={styles.cardTop}>
        {expense.receiptUrl ? (
          <img src={expense.receiptUrl} alt="Receipt" className={styles.receiptThumb} loading="lazy" />
        ) : (
          <div className={styles.receiptThumbEmpty} aria-hidden="true" />
        )}
        <div className={styles.cardTopInfo}>
          <span className={styles.cardAmount}>
            <Money paise={expense.amount} />
          </span>
          <p className={styles.cardMeta}>{expense.requester.name}</p>
          <p className={styles.cardMeta}>
            {CATEGORY_LABEL[expense.category]} · {formatDateOnly(expense.createdAt)}
          </p>
        </div>
      </div>

      {expense.description && <p className={styles.cardDescription}>{expense.description}</p>}

      {expense.status === 'rejected' ? <RejectionNote expense={expense} /> : expense.approval?.reason && <p className={styles.cardMeta}>Reason: {expense.approval.reason}</p>}

      {isOwnRequest && <p className={styles.selfNote}>Needs another approver.</p>}

      {moveError && <ErrorBox error={moveError} />}

      {canDrag && targets.length > 0 && (
        <div className={styles.moveMenu} ref={menuRef}>
          <button type="button" className={styles.moveToggle} onClick={() => setShowMoveMenu((v) => !v)} aria-haspopup="menu" aria-expanded={showMoveMenu}>
            Move to ▸
          </button>
          {showMoveMenu && (
            <div className={styles.moveList} role="menu">
              {targets.map((t) => (
                <button
                  key={t}
                  type="button"
                  role="menuitem"
                  className={styles.moveItem}
                  onClick={() => {
                    setShowMoveMenu(false);
                    onMove(expense.id, t);
                  }}
                >
                  {BOARD_COLUMNS.find((c) => c.status === t)?.label ?? t}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}

function RejectReasonModal({
  open,
  amount,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  amount: number;
  onCancel: () => void;
  onConfirm: (reason: string) => void;
}) {
  const [reason, setReason] = useState('');
  const [validation, setValidation] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setReason('');
      setValidation(null);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, onCancel]);

  if (!open) return null;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (reason.trim().length < MIN_REASON) {
      setValidation(`Give a reason of at least ${MIN_REASON} characters.`);
      return;
    }
    onConfirm(reason.trim());
  };

  return (
    <div className={styles.modalOverlay} onClick={onCancel}>
      <form className={styles.modalCard} role="alertdialog" aria-modal="true" aria-labelledby="reject-modal-title" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h2 id="reject-modal-title" className={styles.modalTitle}>
          Reject <Money paise={amount} />?
        </h2>
        <textarea
          className={styles.textarea}
          placeholder="Reason for rejection (at least 5 characters)"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          autoFocus
        />
        {validation && <p className={styles.error}>{validation}</p>}
        <div className={styles.actions}>
          <button type="button" className={`${styles.button} ${styles.buttonSecondary}`} onClick={onCancel}>
            Cancel
          </button>
          <button type="submit" className={`${styles.button} ${styles.buttonDanger}`}>
            Confirm Reject
          </button>
        </div>
      </form>
    </div>
  );
}
