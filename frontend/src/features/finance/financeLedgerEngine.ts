import { ApiRequestError } from '../../api/client';
import { findUserByEmail } from '../auth/mockUsers';
import { getMockEvent } from '../events/mockEventsStore';
import { listAllMockOrders, type StoredOrder } from '../orders/mockOrdersStore';
import { listAllMockTickets } from '../tickets/mockTicketsStore';
import { listAllMockFundraiserSales } from '../volunteering/mockVolunteeringStore';
import { listAllExpensesForLedger } from '../expenses/mockExpensesStore';
import { MOCK_PLANS } from '../membership/api.mock';
import { getMockProductSize } from '../shop/mockProductsStore';
import { ACCOUNTS } from './accountCodes';
import type {
  AccountLine,
  FinanceSummary,
  LedgerEntry,
  LedgerFilters,
  LedgerKind,
  LedgerLine,
  Reconcile,
  ReconcileCheck,
  Trace,
  TraceEntry,
  TraceSource,
} from './types';

const EXPENSE_ACCOUNT_BY_CATEGORY: Record<string, string> = { event: '5000', fundraiser: '5100', general: '5200' };
const REVENUE_KINDS: LedgerKind[] = ['membership_dues', 'ticket_sale', 'merch_sale', 'fundraiser_sale'];

interface InternalLine {
  account: string;
  debit: number;
  credit: number;
}

interface InternalEntry {
  id: number;
  postedAt: string;
  description: string;
  kind: LedgerKind;
  event: number | null;
  lines: InternalLine[];
  source: TraceSource;
}

function buyerName(email: string): string {
  return findUserByEmail(email)?.name ?? email;
}

function buildTicketEntries(): InternalEntry[] {
  const tickets = listAllMockTickets();
  const groups = new Map<string, typeof tickets>();
  for (const t of tickets) {
    const key = `${t.ownerEmail}|${t.eventId}|${t.tierId}|${t.createdAt}`;
    const group = groups.get(key);
    if (group) group.push(t);
    else groups.set(key, [t]);
  }

  const entries: InternalEntry[] = [];
  let i = 0;
  for (const group of groups.values()) {
    const first = group[0];
    const amount = group.reduce((sum, t) => sum + t.pricePaid, 0);
    const id = 1_000_000 + i++;
    entries.push({
      id,
      postedAt: first.createdAt,
      description: `Tickets: ${first.eventTitle} / ${first.tierName} x${group.length}`,
      kind: 'ticket_sale',
      event: first.eventId,
      lines: [
        { account: '1000', debit: amount, credit: 0 },
        { account: '4100', debit: 0, credit: amount },
      ],
      source: {
        type: 'order_line',
        id,
        label: `${first.ownerName} bought ${group.length} x ${first.tierName} for ${first.eventTitle}`,
        details: {
          order: id,
          buyer: first.ownerName,
          tickets: group.map((t) => ({
            type: 'ticket' as const,
            id: t.id,
            code: t.code,
            holder: t.ownerName,
            pricePaid: t.pricePaid,
            status: t.status,
            checkedInAt: t.checkedInAt ?? null,
          })),
        },
      },
    });
  }
  return entries;
}

function buildOrderEntries(): InternalEntry[] {
  const orders: StoredOrder[] = listAllMockOrders();
  const entries: InternalEntry[] = [];

  for (const order of orders) {
    const buyer = buyerName(order.ownerEmail);

    const membershipLines = order.lines.filter((l) => l.kind === 'membership');
    for (const line of membershipLines) {
      const amount = line.qty * line.unitPrice - line.discount;
      const plan = MOCK_PLANS.find((p) => p.id === line.plan);
      const planName = plan?.name ?? `Plan #${line.plan}`;
      const id = 2_000_000 + order.id;
      entries.push({
        id,
        postedAt: order.createdAt,
        description: `Membership: ${planName}`,
        kind: 'membership_dues',
        event: null,
        lines: [
          { account: '1000', debit: amount, credit: 0 },
          { account: '4000', debit: 0, credit: amount },
        ],
        source: { type: 'payment', id: order.id, label: `${buyer} paid for the ${planName} plan`, details: { payer: buyer, plan: planName } },
      });
    }

    const merchLines = order.lines.filter((l) => l.kind === 'merch');
    if (merchLines.length > 0) {
      const amount = merchLines.reduce((sum, l) => sum + (l.qty * l.unitPrice - l.discount), 0);
      const items = merchLines.map((l) => {
        const resolved = l.productSize !== null ? getMockProductSize(l.productSize) : undefined;
        return {
          product: resolved?.product.name ?? 'Unknown product',
          size: resolved?.size.size ?? '?',
          qty: l.qty,
          unitPrice: l.unitPrice,
        };
      });
      const id = 2_500_000 + order.id;
      entries.push({
        id,
        postedAt: order.createdAt,
        description: `Merch order #${order.id}`,
        kind: 'merch_sale',
        event: null,
        lines: [
          { account: '1000', debit: amount, credit: 0 },
          { account: '4200', debit: 0, credit: amount },
        ],
        source: {
          type: 'order',
          id: order.id,
          label: `${buyer} ordered ${items.length} item${items.length === 1 ? '' : 's'}`,
          details: { order: order.id, buyer, items },
        },
      });
    }
    // Ticket-kind lines are skipped here — they're derived from the tickets
    // store instead (see buildTicketEntries), which also covers the 48
    // seeded tickets that never passed through POST /events/{id}/tickets
    // and so never reached this shared orders store.
  }
  return entries;
}

function buildFundraiserSaleEntries(): InternalEntry[] {
  return listAllMockFundraiserSales().map((sale) => ({
    id: 3_000_000 + sale.id,
    postedAt: sale.recordedAt,
    description: `Fundraiser sale: ${sale.fundraiserTitle}${sale.note ? ` — ${sale.note}` : ''}`,
    kind: 'fundraiser_sale' as const,
    event: null,
    lines: [
      { account: '1000', debit: sale.amount, credit: 0 },
      { account: '4300', debit: 0, credit: sale.amount },
    ],
    source: {
      type: 'fundraiser_sale' as const,
      id: sale.id,
      label: `${sale.fundraiserTitle} sale recorded`,
      details: { fundraiser: sale.fundraiserTitle, note: sale.note },
    },
  }));
}

function buildExpenseEntries(): InternalEntry[] {
  const expenses = listAllExpensesForLedger();
  const entries: InternalEntry[] = [];

  for (const expense of expenses) {
    if (!expense.approval || expense.approval.decision !== 'approved') continue;
    const account = EXPENSE_ACCOUNT_BY_CATEGORY[expense.category] ?? '5200';
    const event = expense.category === 'event' ? expense.event : null;
    const source: TraceSource = {
      type: 'expense_request',
      id: expense.id,
      label: `${expense.requesterName}: ${expense.description}`,
      details: {
        requester: expense.requesterName,
        description: expense.description,
        receiptUrl: expense.receiptUrl,
        approvedBy: expense.approval.approver.name,
      },
    };

    entries.push({
      id: 4_000_000 + expense.id,
      postedAt: expense.approval.decidedAt,
      description: `Expense approved: ${expense.description}`,
      kind: 'expense_approved',
      event,
      lines: [
        { account, debit: expense.amount, credit: 0 },
        { account: '2000', debit: 0, credit: expense.amount },
      ],
      source,
    });

    if (expense.status === 'paid') {
      // The expense object has no separate "paid at" timestamp, so this is
      // pinned a fixed day after the approval decision — stable across
      // repeated reads instead of drifting with Date.now() on every call.
      const paidAt = new Date(new Date(expense.approval.decidedAt).getTime() + 86_400_000).toISOString();
      entries.push({
        id: 4_500_000 + expense.id,
        postedAt: paidAt,
        description: `Expense paid: ${expense.description}`,
        kind: 'expense_paid',
        event,
        lines: [
          { account: '2000', debit: expense.amount, credit: 0 },
          { account: '1000', debit: 0, credit: expense.amount },
        ],
        source,
      });
    }
  }
  return entries;
}

function buildAllEntries(): InternalEntry[] {
  const entries = [...buildTicketEntries(), ...buildOrderEntries(), ...buildFundraiserSaleEntries(), ...buildExpenseEntries()];
  entries.sort((a, b) => b.postedAt.localeCompare(a.postedAt) || b.id - a.id);
  return entries;
}

function accountSignedAmount(code: string, line: InternalLine): number {
  const type = ACCOUNTS[code]?.type;
  if (type === 'revenue' || type === 'liability') return line.credit - line.debit;
  return line.debit - line.credit;
}

function toPublicLines(lines: InternalLine[]): LedgerLine[] {
  return lines.map((l, i) => ({
    id: i + 1,
    account: ACCOUNTS[l.account] ?? { code: l.account, name: l.account, type: 'asset' },
    debit: l.debit,
    credit: l.credit,
  }));
}

function toPublicLedgerEntry(e: InternalEntry): LedgerEntry {
  return {
    id: e.id,
    postedAt: e.postedAt,
    description: e.description,
    sourceType: e.source.type,
    sourceId: e.source.id,
    kind: e.kind,
    event: e.event,
    reverses: null,
    lines: toPublicLines(e.lines),
  };
}

function byAccountBreakdown(entries: InternalEntry[], codes: string[]): AccountLine[] {
  const totals = new Map<string, number>();
  for (const e of entries) {
    for (const line of e.lines) {
      if (!codes.includes(line.account)) continue;
      totals.set(line.account, (totals.get(line.account) ?? 0) + accountSignedAmount(line.account, line));
    }
  }
  return codes
    .filter((c) => (totals.get(c) ?? 0) !== 0)
    .map((c) => ({ code: c, name: ACCOUNTS[c].name, amount: totals.get(c) ?? 0 }));
}

export function computeSummary(): FinanceSummary {
  const entries = buildAllEntries();
  const revenueCodes = ['4000', '4100', '4200', '4300'];
  const expenseCodes = ['5000', '5100', '5200'];

  const cameInByAccount = byAccountBreakdown(entries, revenueCodes);
  const wentOutByAccount = byAccountBreakdown(
    entries.filter((e) => e.kind === 'expense_approved'),
    expenseCodes,
  );
  const cameInTotal = cameInByAccount.reduce((s, a) => s + a.amount, 0);
  const wentOutTotal = wentOutByAccount.reduce((s, a) => s + a.amount, 0);
  const net = cameInTotal - wentOutTotal;

  const paidOut = entries.filter((e) => e.kind === 'expense_paid').reduce((s, e) => s + e.lines.find((l) => l.account === '1000')!.credit, 0);
  const cash = cameInTotal - paidOut;
  const payable = wentOutTotal - paidOut;

  return { cameIn: { total: cameInTotal, byAccount: cameInByAccount }, wentOut: { total: wentOutTotal, byAccount: wentOutByAccount }, net, cash, payable };
}

/** Real expenses posted against this event — plugged into GET /events/{id}/pnl
 * (features/events/api.mock.ts) now that Phase 4/5 give it somewhere to come
 * from; the contract itself notes "expenses stays empty until reimbursements
 * post to the ledger," which is exactly this. */
export function computeEventExpenses(eventId: number): { total: number; byAccount: AccountLine[] } {
  const entries = buildAllEntries().filter((e) => e.kind === 'expense_approved' && e.event === eventId);
  const byAccount = byAccountBreakdown(entries, ['5000', '5100', '5200']);
  return { total: byAccount.reduce((s, a) => s + a.amount, 0), byAccount };
}

export function listLedger(filters: LedgerFilters, page: number, pageSize: number): { count: number; results: LedgerEntry[] } {
  let entries = buildAllEntries();
  if (filters.account) entries = entries.filter((e) => e.lines.some((l) => l.account === filters.account));
  if (filters.event !== undefined) entries = entries.filter((e) => e.event === filters.event);
  if (filters.kind) entries = entries.filter((e) => e.kind === filters.kind);

  const start = (page - 1) * pageSize;
  return { count: entries.length, results: entries.slice(start, start + pageSize).map(toPublicLedgerEntry) };
}

export function computeReconcile(): Reconcile {
  const entries = buildAllEntries();
  const summary = computeSummary();

  const debitTotal = entries.reduce((s, e) => s + e.lines.reduce((ls, l) => ls + l.debit, 0), 0);
  const creditTotal = entries.reduce((s, e) => s + e.lines.reduce((ls, l) => ls + l.credit, 0), 0);

  const ticketRevenueFromSource = listAllMockTickets()
    .filter((t) => t.status !== 'cancelled')
    .reduce((s, t) => s + t.pricePaid, 0);
  const ticketRevenueFromLedger = summary.cameIn.byAccount.find((a) => a.code === '4100')?.amount ?? 0;

  const merchRevenueFromSource = listAllMockOrders()
    .flatMap((o) => o.lines)
    .filter((l) => l.kind === 'merch')
    .reduce((s, l) => s + (l.qty * l.unitPrice - l.discount), 0);
  const merchRevenueFromLedger = summary.cameIn.byAccount.find((a) => a.code === '4200')?.amount ?? 0;

  const duesFromSource = listAllMockOrders()
    .flatMap((o) => o.lines)
    .filter((l) => l.kind === 'membership')
    .reduce((s, l) => s + (l.qty * l.unitPrice - l.discount), 0);
  const duesFromLedger = summary.cameIn.byAccount.find((a) => a.code === '4000')?.amount ?? 0;

  const fundraiserFromSource = listAllMockFundraiserSales().reduce((s, sale) => s + sale.amount, 0);
  const fundraiserFromLedger = summary.cameIn.byAccount.find((a) => a.code === '4300')?.amount ?? 0;

  const allExpenses = listAllExpensesForLedger();
  const approvedFromSource = allExpenses
    .filter((e) => e.status === 'approved' || e.status === 'paid')
    .reduce((s, e) => s + e.amount, 0);
  const payableFromSource = allExpenses.filter((e) => e.status === 'approved').reduce((s, e) => s + e.amount, 0);

  const checks: ReconcileCheck[] = [
    { name: 'Ledger debits equal credits', ok: debitTotal === creditTotal, expected: debitTotal, actual: creditTotal },
    { name: 'Ticket revenue equals paid ticket records', ok: ticketRevenueFromSource === ticketRevenueFromLedger, expected: ticketRevenueFromSource, actual: ticketRevenueFromLedger },
    { name: 'Merchandise revenue equals paid merch order lines', ok: merchRevenueFromSource === merchRevenueFromLedger, expected: merchRevenueFromSource, actual: merchRevenueFromLedger },
    { name: 'Membership dues equal paid membership order lines', ok: duesFromSource === duesFromLedger, expected: duesFromSource, actual: duesFromLedger },
    { name: 'Fundraiser revenue equals recorded sales', ok: fundraiserFromSource === fundraiserFromLedger, expected: fundraiserFromSource, actual: fundraiserFromLedger },
    { name: 'Went out equals approved or paid expense requests', ok: approvedFromSource === summary.wentOut.total, expected: approvedFromSource, actual: summary.wentOut.total },
    { name: 'Payable equals approved, not-yet-paid expense requests', ok: payableFromSource === summary.payable, expected: payableFromSource, actual: summary.payable },
    { name: 'Cash equals net plus payable', ok: summary.cash === summary.net + summary.payable, expected: summary.net + summary.payable, actual: summary.cash },
  ];

  return { ok: checks.every((c) => c.ok), checks };
}

function unknownFigure(): never {
  throw new ApiRequestError({
    code: 'validation_error',
    message: 'Unknown figure.',
    field: 'figure',
    errors: [{ field: 'figure', code: 'unknown_figure', message: 'Unknown figure.' }],
  });
}

function entriesToTrace(figure: string, label: string, chosen: { entry: InternalEntry; amount: number }[]): Trace {
  chosen.sort((a, b) => b.entry.postedAt.localeCompare(a.entry.postedAt) || b.entry.id - a.entry.id);
  const entryCount = chosen.length;
  const capped = chosen.slice(0, 200);
  const entries: TraceEntry[] = capped.map(({ entry, amount }) => ({
    id: entry.id,
    postedAt: entry.postedAt,
    description: entry.description,
    kind: entry.kind,
    amount,
    lines: toPublicLines(entry.lines),
    source: entry.source,
  }));
  const total = chosen.reduce((s, c) => s + c.amount, 0);
  return { figure, label, total, entryCount, entries };
}

export function trace(figure: string): Trace {
  const entries = buildAllEntries();

  if (figure === 'came_in') {
    return entriesToTrace(
      figure,
      'Came In',
      entries.filter((e) => REVENUE_KINDS.includes(e.kind)).map((entry) => ({ entry, amount: entry.lines.find((l) => l.credit > 0)!.credit })),
    );
  }
  if (figure === 'went_out') {
    return entriesToTrace(
      figure,
      'Went Out',
      entries.filter((e) => e.kind === 'expense_approved').map((entry) => ({ entry, amount: entry.lines.find((l) => l.debit > 0 && l.account !== '2000')!.debit })),
    );
  }
  if (figure === 'cash') {
    return entriesToTrace(
      figure,
      'Cash',
      entries.filter((e) => e.lines.some((l) => l.account === '1000')).map((entry) => ({ entry, amount: accountSignedAmount('1000', entry.lines.find((l) => l.account === '1000')!) })),
    );
  }
  if (figure === 'payable') {
    return entriesToTrace(
      figure,
      'Payable',
      entries.filter((e) => e.lines.some((l) => l.account === '2000')).map((entry) => ({ entry, amount: accountSignedAmount('2000', entry.lines.find((l) => l.account === '2000')!) })),
    );
  }
  if (figure.startsWith('account:')) {
    const code = figure.slice('account:'.length);
    const account = ACCOUNTS[code];
    if (!account) unknownFigure();
    return entriesToTrace(
      figure,
      account.name,
      entries.filter((e) => e.lines.some((l) => l.account === code)).map((entry) => ({ entry, amount: accountSignedAmount(code, entry.lines.find((l) => l.account === code)!) })),
    );
  }
  if (figure.startsWith('event:')) {
    const parts = figure.split(':');
    const eventId = Number(parts[1]);
    const sub = parts[2];
    const event = getMockEvent(eventId);
    if (!event || Number.isNaN(eventId) || !['revenue', 'expenses', 'profit'].includes(sub)) unknownFigure();

    if (sub === 'revenue') {
      return entriesToTrace(
        figure,
        `${event!.title}: revenue`,
        entries.filter((e) => e.event === eventId && REVENUE_KINDS.includes(e.kind)).map((entry) => ({ entry, amount: entry.lines.find((l) => l.credit > 0)!.credit })),
      );
    }
    if (sub === 'expenses') {
      return entriesToTrace(
        figure,
        `${event!.title}: expenses`,
        entries
          .filter((e) => e.event === eventId && e.kind === 'expense_approved')
          .map((entry) => ({ entry, amount: entry.lines.find((l) => l.debit > 0 && l.account !== '2000')!.debit })),
      );
    }
    // profit: revenue positive, expenses negative, per the contract's note.
    const revenueEntries = entries
      .filter((e) => e.event === eventId && REVENUE_KINDS.includes(e.kind))
      .map((entry) => ({ entry, amount: entry.lines.find((l) => l.credit > 0)!.credit }));
    const expenseEntries = entries
      .filter((e) => e.event === eventId && e.kind === 'expense_approved')
      .map((entry) => ({ entry, amount: -entry.lines.find((l) => l.debit > 0 && l.account !== '2000')!.debit }));
    return entriesToTrace(figure, `${event!.title}: profit`, [...revenueEntries, ...expenseEntries]);
  }

  unknownFigure();
}
