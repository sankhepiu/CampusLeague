import { useEffect, useRef, useState, type DragEvent } from 'react';
import { Panel } from '../../components/Panel/Panel';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { Money } from '../../components/Money/Money';
import type { ApiError } from '../../api/client';
import { useAsync } from '../../core/hooks/useAsync';
import { accentVarForFeature } from '../../core/config/accents';
import { formatDateTime } from '../../core/utils/formatDateTime';
import { expensesApi } from './api';
import type { Expense, ExpenseStatus } from './types';
import styles from './ExpenseKanban.module.scss';

const COLUMNS: { status: ExpenseStatus; label: string }[] = [
  { status: 'submitted', label: 'Submitted' },
  { status: 'approved', label: 'Approved' },
  { status: 'paid', label: 'Paid' },
  { status: 'rejected', label: 'Rejected' },
];
const COLUMN_LABEL: Record<ExpenseStatus, string> = Object.fromEntries(COLUMNS.map((c) => [c.status, c.label])) as Record<ExpenseStatus, string>;
const CATEGORY_LABEL: Record<string, string> = { event: 'Event', fundraiser: 'Fundraiser', general: 'General' };

/** The only drags the server actually allows — everything else snaps back.
 * Paid and rejected are terminal: nowhere left to drag them. */
const ALLOWED_MOVES: Partial<Record<ExpenseStatus, ExpenseStatus[]>> = {
  submitted: ['approved', 'rejected'],
  approved: ['paid'],
};

const DRAG_MIME = 'text/plain';

function isImageReceipt(url: string): boolean {
  // Real uploads are /media/receipts/<name>.<ext>; the mock's seed data uses
  // an inline data: URI placeholder image instead of a real file.
  return /\.(jpe?g|png|gif|webp)$/i.test(url) || url.startsWith('data:image/');
}

/** The approval queue needs every status bucketed into columns at once, not
 * one filtered page at a time, so this follows `next` the same way
 * features/members/api.real.ts does for its own full-list use cases. */
async function fetchAllExpenses(): Promise<Expense[]> {
  const MAX_PAGES = 50;
  const all: Expense[] = [];
  for (let page = 1; page <= MAX_PAGES; page += 1) {
    const result = await expensesApi.listAll({}, page);
    all.push(...result.results);
    if (!result.next) break;
  }
  return all;
}

function moveErrorMessage(err: ApiError): string {
  if (err.code === 'self_approval') return "This is your own request — it needs another approver.";
  if (err.code === 'invalid_status') return 'This request was already decided elsewhere — refreshing.';
  return err.message;
}

export function ExpenseKanban({ currentUserId }: { currentUserId: number | null }) {
  const { status, data: expenses, error, reload } = useAsync(fetchAllExpenses, []);

  // Local, optimistically-mutable mirror — same pattern as the volunteering
  // Kanban board, so a move responds instantly instead of waiting on a
  // round trip (and re-fetching the whole queue would flash a spinner).
  const [items, setItems] = useState<Expense[]>([]);
  useEffect(() => {
    if (expenses) setItems(expenses);
  }, [expenses]);

  const [draggingId, setDraggingId] = useState<number | null>(null);
  const [dragOverColumn, setDragOverColumn] = useState<ExpenseStatus | null>(null);
  const [moveError, setMoveError] = useState<{ id: number; message: string } | null>(null);
  const [rejectTarget, setRejectTarget] = useState<Expense | null>(null);

  if (status === 'loading') return <Spinner fullPage label="Loading requests…" />;
  if (status === 'error') return <ErrorBox error={error!} onRetry={reload} />;

  const applyMove = (id: number, next: ExpenseStatus) => setItems((list) => list.map((e) => (e.id === id ? { ...e, status: next } : e)));
  const revertMove = (id: number, prev: ExpenseStatus) => setItems((list) => list.map((e) => (e.id === id ? { ...e, status: prev } : e)));

  const doApprove = async (expense: Expense) => {
    setMoveError(null);
    applyMove(expense.id, 'approved');
    try {
      await expensesApi.approve(expense.id);
    } catch (err) {
      revertMove(expense.id, expense.status);
      const apiError = err as ApiError;
      setMoveError({ id: expense.id, message: moveErrorMessage(apiError) });
      if (apiError.code === 'invalid_status') reload();
    }
  };

  const doMarkPaid = async (expense: Expense) => {
    setMoveError(null);
    applyMove(expense.id, 'paid');
    try {
      await expensesApi.markPaid(expense.id);
    } catch (err) {
      revertMove(expense.id, expense.status);
      const apiError = err as ApiError;
      setMoveError({ id: expense.id, message: moveErrorMessage(apiError) });
      if (apiError.code === 'invalid_status') reload();
    }
  };

  const doReject = async (expense: Expense, reason: string) => {
    setMoveError(null);
    applyMove(expense.id, 'rejected');
    try {
      await expensesApi.reject(expense.id, reason);
    } catch (err) {
      revertMove(expense.id, expense.status);
      const apiError = err as ApiError;
      setMoveError({ id: expense.id, message: moveErrorMessage(apiError) });
      if (apiError.code === 'invalid_status') reload();
    } finally {
      setRejectTarget(null);
    }
  };

  const attemptMove = (expense: Expense, target: ExpenseStatus) => {
    if (target === expense.status) return;
    const allowed = ALLOWED_MOVES[expense.status]?.includes(target) ?? false;
    if (!allowed) {
      setMoveError({ id: expense.id, message: `Can't move from ${COLUMN_LABEL[expense.status]} to ${COLUMN_LABEL[target]}.` });
      return;
    }
    if (target === 'rejected') {
      // Reject always needs a reason first — nothing moves until the modal
      // is confirmed, so a cancelled drag never leaves the card stranded.
      setRejectTarget(expense);
      return;
    }
    if (target === 'approved') void doApprove(expense);
    if (target === 'paid') void doMarkPaid(expense);
  };

  return (
    <>
      <div className={styles.columns}>
        {COLUMNS.map((col) => {
          const colItems = items.filter((e) => e.status === col.status);
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
                const id = Number(e.dataTransfer.getData(DRAG_MIME));
                const expense = items.find((x) => x.id === id);
                if (expense) attemptMove(expense, col.status);
              }}
            >
              <h3 className={styles.columnTitle}>
                {col.label} <span className={styles.columnCount}>({colItems.length})</span>
              </h3>
              {colItems.map((expense) => (
                <ExpenseCard
                  key={expense.id}
                  expense={expense}
                  isOwn={currentUserId !== null && expense.requester.id === currentUserId}
                  moveError={moveError?.id === expense.id ? moveError.message : null}
                  onDragStart={() => setDraggingId(expense.id)}
                  onDragEnd={() => {
                    setDraggingId(null);
                    setDragOverColumn(null);
                  }}
                  onMove={(target) => attemptMove(expense, target)}
                />
              ))}
              {colItems.length === 0 && <p className={styles.empty}>Nothing here.</p>}
            </div>
          );
        })}
      </div>

      {rejectTarget && (
        <RejectReasonModal expense={rejectTarget} onCancel={() => setRejectTarget(null)} onConfirm={(reason) => void doReject(rejectTarget, reason)} />
      )}
    </>
  );
}

function ExpenseCard({
  expense,
  isOwn,
  moveError,
  onDragStart,
  onDragEnd,
  onMove,
}: {
  expense: Expense;
  isOwn: boolean;
  moveError: string | null;
  onDragStart: () => void;
  onDragEnd: () => void;
  onMove: (target: ExpenseStatus) => void;
}) {
  const [showMoveMenu, setShowMoveMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!showMoveMenu) return;
    const onClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setShowMoveMenu(false);
    };
    document.addEventListener('click', onClickOutside);
    return () => document.removeEventListener('click', onClickOutside);
  }, [showMoveMenu]);

  const destinations = isOwn ? [] : (ALLOWED_MOVES[expense.status] ?? []);
  const canDrag = destinations.length > 0;

  return (
    <Panel
      className={styles.card}
      accent={accentVarForFeature('expenses')}
      draggable={canDrag}
      onDragStart={(e: DragEvent<HTMLDivElement>) => {
        e.dataTransfer.setData(DRAG_MIME, String(expense.id));
        e.dataTransfer.effectAllowed = 'move';
        onDragStart();
      }}
      onDragEnd={onDragEnd}
    >
      <div className={styles.cardHeader}>
        {canDrag && (
          <span className={styles.dragHandle} aria-hidden="true" title="Drag to move">
            ⠿
          </span>
        )}
        <span className={styles.amount}>
          <Money paise={expense.amount} />
        </span>
      </div>
      <p className={styles.meta}>
        {expense.requester.name} · {CATEGORY_LABEL[expense.category] ?? expense.category}
      </p>
      <p className={styles.meta}>{formatDateTime(expense.createdAt)}</p>

      {expense.receiptUrl &&
        (isImageReceipt(expense.receiptUrl) ? (
          <a href={expense.receiptUrl} target="_blank" rel="noreferrer">
            <img src={expense.receiptUrl} alt="Receipt" className={styles.thumb} />
          </a>
        ) : (
          <a href={expense.receiptUrl} target="_blank" rel="noreferrer" className={styles.receiptLink}>
            View Receipt
          </a>
        ))}

      {isOwn && <p className={styles.selfNote}>Your request — needs another approver.</p>}

      {moveError && <ErrorBox error={moveError} />}

      {canDrag && (
        <div className={styles.moveMenu} ref={menuRef}>
          <button type="button" className={styles.moveToggle} onClick={() => setShowMoveMenu((v) => !v)} aria-haspopup="menu" aria-expanded={showMoveMenu}>
            Move to ▸
          </button>
          {showMoveMenu && (
            <div className={styles.moveList} role="menu">
              {destinations.map((d) => (
                <button
                  key={d}
                  type="button"
                  role="menuitem"
                  className={styles.moveItem}
                  onClick={() => {
                    setShowMoveMenu(false);
                    onMove(d);
                  }}
                >
                  {COLUMN_LABEL[d]}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}

function RejectReasonModal({ expense, onCancel, onConfirm }: { expense: Expense; onCancel: () => void; onConfirm: (reason: string) => void }) {
  const [reason, setReason] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onCancel]);

  const confirm = () => {
    if (!reason.trim()) {
      setValidationError('A reason is required to reject a request.');
      return;
    }
    onConfirm(reason.trim());
  };

  return (
    <div className={styles.overlay} onClick={onCancel}>
      <div className={styles.modalCard} role="alertdialog" aria-modal="true" aria-labelledby="reject-modal-title" onClick={(e) => e.stopPropagation()}>
        <h2 id="reject-modal-title" className={styles.modalTitle}>
          Reject this request?
        </h2>
        <p className={styles.meta}>
          <Money paise={expense.amount} /> · {expense.requester.name}
        </p>
        <textarea
          className={styles.textarea}
          placeholder="Reason for rejection (required)"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          autoFocus
        />
        {validationError && <p className={styles.error}>{validationError}</p>}
        <div className={styles.modalActions}>
          <button type="button" className={styles.moveToggle} onClick={onCancel}>
            Cancel
          </button>
          <button type="button" className={styles.buttonDanger} onClick={confirm}>
            Confirm Reject
          </button>
        </div>
      </div>
    </div>
  );
}
