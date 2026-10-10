import { ApiRequestError } from '../../api/client';
import { getCurrentMockUser } from '../auth/mockUsers';
import { validateReceiptFile } from './receiptValidation';
import type { ApprovalDecision, Expense, ExpenseCategory, ExpenseStatus } from './types';

interface MockExpense extends Omit<Expense, 'requester'> {
  requesterId: number;
  requesterName: string;
}

const STORE_KEY = 'campusleague.mock.expenses';
const APPROVAL_ROLES = ['president', 'treasurer'];

/** Receipt files are kept as in-memory object URLs, not persisted to
 * localStorage — a 5MB file as base64 risks blowing the ~5-10MB per-origin
 * quota outright. This means uploaded receipts only stay viewable for the
 * current browser session/reload, a known mock-only limitation (noted in
 * the Phase 4 report), not something the real backend would have. */
const objectUrls = new Map<number, string>();

// A tiny inline placeholder image so seeded receipts actually open to
// something, instead of a dead link — real submissions use a genuine
// object URL from the uploaded file (see objectUrls below).
const SEED_RECEIPT = 'data:image/svg+xml;base64,' + btoa(
  '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="400"><rect width="300" height="400" fill="#fff"/>' +
    '<text x="20" y="40" font-family="monospace" font-size="18">RECEIPT (seed demo data)</text>' +
    '<text x="20" y="80" font-family="monospace" font-size="14">No real file was uploaded for this</text>' +
    '<text x="20" y="100" font-family="monospace" font-size="14">pre-seeded reimbursement.</text></svg>',
);

/** Two already-decided reimbursements so the finance ledger (Phase 5) has a
 * real expense to show and drill into from a fresh browser profile — one
 * paid and event-tagged (so GET /events/1/pnl has expenses to report, and
 * the Coin Trail reaches a receipt), one approved-but-unpaid so `payable`
 * isn't zero. Matches the contract's own ledger example amount/description
 * ("Expense approved: Venue deposit", 500000) and its summary example's
 * payable figure (135000) exactly, where that was easy to do. */
function seedExpenses(): MockExpense[] {
  const daysAgo = (n: number) => new Date(Date.now() - n * 86_400_000).toISOString();
  return [
    {
      id: 1,
      requesterId: 6,
      requesterName: 'Eva Events',
      amount: 500000,
      category: 'event',
      event: 1,
      fundraiser: null,
      description: 'Venue deposit',
      receiptUrl: SEED_RECEIPT,
      status: 'paid',
      createdAt: daysAgo(18),
      approval: { decision: 'approved', reason: null, decidedAt: daysAgo(17), approver: { id: 5, name: 'Tom Treasurer' } },
    },
    {
      id: 2,
      requesterId: 6,
      requesterName: 'Eva Events',
      amount: 135000,
      category: 'general',
      event: null,
      fundraiser: null,
      description: 'Printing and signage for spring recruitment',
      receiptUrl: SEED_RECEIPT,
      status: 'approved',
      createdAt: daysAgo(6),
      approval: { decision: 'approved', reason: null, decidedAt: daysAgo(5), approver: { id: 4, name: 'Pia President' } },
    },
  ];
}

function loadStore(): MockExpense[] {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) return JSON.parse(raw) as MockExpense[];
  } catch {
    /* storage unavailable or corrupt */
  }
  const seeded = seedExpenses();
  saveStore(seeded);
  return seeded;
}

function saveStore(items: MockExpense[]): void {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(items));
  } catch {
    /* storage unavailable */
  }
}

function toPublic(e: MockExpense): Expense {
  const { requesterId, requesterName, ...rest } = e;
  return { ...rest, requester: { id: requesterId, name: requesterName }, receiptUrl: objectUrls.get(e.id) ?? e.receiptUrl };
}

function requireUser() {
  const user = getCurrentMockUser();
  if (!user) throw new ApiRequestError({ code: 'not_authenticated', message: 'No active session.' });
  return user;
}

function requireApprover() {
  const user = requireUser();
  if (!user.roles.some((r) => APPROVAL_ROLES.includes(r))) {
    throw new ApiRequestError({ code: 'permission_denied', message: 'Only the president or treasurer can decide requests.' });
  }
  return user;
}

export const mockExpenses = {
  submit(params: {
    amountPaise: number;
    category: ExpenseCategory;
    description: string;
    receiptFile: File;
    event?: number;
    fundraiser?: number;
  }): MockExpense {
    const user = requireUser();

    const errors: { field: string; code: string; message: string }[] = [];
    if (!params.receiptFile) errors.push({ field: 'receipt_file', code: 'required', message: 'A receipt is required.' });
    else {
      const fileError = validateReceiptFile(params.receiptFile);
      if (fileError) errors.push(fileError);
    }
    if (!params.description.trim()) errors.push({ field: 'description', code: 'blank', message: 'This field may not be blank.' });
    if (params.description.length > 500) errors.push({ field: 'description', code: 'max_length', message: 'Description must be 500 characters or fewer.' });
    if (!(params.amountPaise > 0)) errors.push({ field: 'amount', code: 'invalid', message: 'Amount must be greater than zero.' });

    if (params.category === 'event') {
      if (!params.event) errors.push({ field: 'event', code: 'event_required', message: 'Select the event this expense is for.' });
      if (params.fundraiser) errors.push({ field: 'fundraiser', code: 'tag_not_allowed', message: 'An event expense cannot also tag a fundraiser.' });
    } else if (params.category === 'fundraiser') {
      if (!params.fundraiser) errors.push({ field: 'fundraiser', code: 'fundraiser_required', message: 'Select the fundraiser this expense is for.' });
      if (params.event) errors.push({ field: 'event', code: 'tag_not_allowed', message: 'A fundraiser expense cannot also tag an event.' });
    } else {
      if (params.event) errors.push({ field: 'event', code: 'tag_not_allowed', message: 'A general expense cannot tag an event.' });
      if (params.fundraiser) errors.push({ field: 'fundraiser', code: 'tag_not_allowed', message: 'A general expense cannot tag a fundraiser.' });
    }

    if (errors.length > 0) {
      throw new ApiRequestError({ code: 'validation_error', message: errors[0].message, field: errors[0].field, errors });
    }

    const items = loadStore();
    const id = items.reduce((max, e) => Math.max(max, e.id), 0) + 1;
    const expense: MockExpense = {
      id,
      requesterId: user.id,
      requesterName: user.name,
      amount: params.amountPaise,
      category: params.category,
      event: params.event ?? null,
      fundraiser: params.fundraiser ?? null,
      description: params.description,
      receiptUrl: '',
      status: 'submitted',
      createdAt: new Date().toISOString(),
      approval: null,
    };
    objectUrls.set(id, URL.createObjectURL(params.receiptFile));
    items.push(expense);
    saveStore(items);
    return expense;
  },

  listMine(): MockExpense[] {
    const user = requireUser();
    return loadStore()
      .filter((e) => e.requesterId === user.id)
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  },

  listAll(status?: ExpenseStatus): MockExpense[] {
    requireApprover();
    return loadStore()
      .filter((e) => !status || e.status === status)
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  },

  decide(id: number, decision: ApprovalDecision, reason: string | undefined): MockExpense {
    const approver = requireApprover();
    const items = loadStore();
    const expense = items.find((e) => e.id === id);
    if (!expense) throw new ApiRequestError({ code: 'not_found', message: 'No such request.' });
    if (expense.requesterId === approver.id) {
      throw new ApiRequestError({ code: 'self_approval', message: 'You cannot decide your own request.' });
    }
    if (expense.status !== 'submitted') {
      throw new ApiRequestError({ code: 'invalid_status', message: 'This request was already decided.' });
    }
    if (decision === 'rejected' && !reason?.trim()) {
      throw new ApiRequestError({ code: 'validation_error', message: 'A reason is required to reject a request.', field: 'reason' });
    }

    expense.status = decision === 'approved' ? 'approved' : 'rejected';
    expense.approval = { decision, reason: reason?.trim() || null, decidedAt: new Date().toISOString(), approver: { id: approver.id, name: approver.name } };
    saveStore(items);
    return expense;
  },

  markPaid(id: number): MockExpense {
    requireApprover();
    const items = loadStore();
    const expense = items.find((e) => e.id === id);
    if (!expense) throw new ApiRequestError({ code: 'not_found', message: 'No such request.' });
    if (expense.status !== 'approved') {
      throw new ApiRequestError({ code: 'invalid_status', message: 'Only an approved request can be marked paid.' });
    }
    expense.status = 'paid';
    saveStore(items);
    return expense;
  },
};

export { toPublic as toPublicExpense };

/** Unguarded read of every expense, decided or not — for internal reuse by
 * OTHER already-permissioned mock engines (the finance ledger, and
 * GET /events/{id}/pnl, open to event managers too) that need the raw data
 * without re-running GET /expenses's own "president or treasurer" check,
 * which would otherwise wrongly block an event manager's P&L view. Not a
 * stand-in for `mockExpenses.listAll()`, which is that real endpoint. */
export function listAllExpensesForLedger(): MockExpense[] {
  return loadStore();
}
