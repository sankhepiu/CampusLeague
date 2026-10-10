import { request, type Paginated } from '../../api/client';
import type {
  AccountLine,
  FinanceSummary,
  LedgerAccount,
  LedgerEntry,
  LedgerFilters,
  LedgerLine,
  Reconcile,
  Trace,
  TraceEntry,
  TraceSource,
  TraceSourceType,
} from './types';

interface WireAccountLine {
  code: string;
  name: string;
  amount: number;
}

interface WireFigureTotal {
  total: number;
  by_account: WireAccountLine[];
}

interface WireSummary {
  came_in: WireFigureTotal;
  went_out: WireFigureTotal;
  net: number;
  cash: number;
  payable: number;
}

interface WireLedgerAccount {
  code: string;
  name: string;
  type: LedgerAccount['type'];
}

interface WireLedgerLine {
  id: number;
  account: WireLedgerAccount;
  debit: number;
  credit: number;
}

interface WireLedgerEntry {
  id: number;
  posted_at: string;
  description: string;
  source_type: LedgerEntry['sourceType'];
  source_id: number;
  kind: LedgerEntry['kind'];
  event: number | null;
  reverses: number | null;
  lines: WireLedgerLine[];
}

interface WireReconcileCheck {
  name: string;
  ok: boolean;
  expected: number;
  actual: number;
}

interface WireReconcile {
  ok: boolean;
  checks: WireReconcileCheck[];
}

interface WireTicketDetail {
  type: 'ticket';
  id: number;
  code: string;
  holder: string;
  price_paid: number;
  status: string;
  checked_in_at: string | null;
}

interface WireMerchItem {
  product: string;
  size: string;
  qty: number;
  unit_price: number;
}

interface WireSource {
  type: TraceSourceType;
  id: number;
  label: string;
  details: {
    // order_line (tickets)
    order?: number;
    buyer?: string;
    tickets?: WireTicketDetail[];
    // order (merch) also uses order/buyer above, plus:
    items?: WireMerchItem[];
    // payment (membership dues)
    payer?: string;
    plan?: string;
    // expense_request
    requester?: string;
    description?: string;
    receipt_url?: string;
    approved_by?: string | null;
    // fundraiser_sale
    fundraiser?: string;
    note?: string;
  };
}

function fromWireSource(s: WireSource): TraceSource {
  const d = s.details;
  switch (s.type) {
    case 'order_line':
      return { type: s.type, id: s.id, label: s.label, details: { order: d.order!, buyer: d.buyer!, tickets: (d.tickets ?? []).map((t) => ({ type: 'ticket', id: t.id, code: t.code, holder: t.holder, pricePaid: t.price_paid, status: t.status, checkedInAt: t.checked_in_at })) } };
    case 'order':
      // GAP: `order` is missing from the live backend's merch order source
      // today — left optional rather than force-unwrapped (see types.ts).
      return { type: s.type, id: s.id, label: s.label, details: { order: d.order, buyer: d.buyer!, items: (d.items ?? []).map((i) => ({ product: i.product, size: i.size, qty: i.qty, unitPrice: i.unit_price })) } };
    case 'payment':
      return { type: s.type, id: s.id, label: s.label, details: { payer: d.payer!, plan: d.plan! } };
    case 'expense_request':
      // GAP: `description`/`approved_by` are missing from the live backend's
      // expense_request source today — left optional rather than
      // force-unwrapped (see types.ts).
      return { type: s.type, id: s.id, label: s.label, details: { requester: d.requester!, description: d.description, receiptUrl: d.receipt_url!, approvedBy: d.approved_by } };
    case 'fundraiser_sale':
      return { type: s.type, id: s.id, label: s.label, details: { fundraiser: d.fundraiser!, note: d.note ?? '' } };
  }
}

interface WireTraceEntry {
  id: number;
  posted_at: string;
  description: string;
  kind: TraceEntry['kind'];
  amount: number;
  lines: WireLedgerLine[];
  source: WireSource;
}

interface WireTrace {
  figure: string;
  label: string;
  total: number;
  entry_count: number;
  entries: WireTraceEntry[];
}

function fromWireAccountLine(a: WireAccountLine): AccountLine {
  return { code: a.code, name: a.name, amount: a.amount };
}

function fromWireLines(lines: WireLedgerLine[]): LedgerLine[] {
  return lines.map((l) => ({ id: l.id, account: l.account, debit: l.debit, credit: l.credit }));
}

function fromWireLedgerEntry(e: WireLedgerEntry): LedgerEntry {
  return {
    id: e.id,
    postedAt: e.posted_at,
    description: e.description,
    sourceType: e.source_type,
    sourceId: e.source_id,
    kind: e.kind,
    event: e.event,
    reverses: e.reverses,
    lines: fromWireLines(e.lines),
  };
}

export const realFinanceApi = {
  async summary(): Promise<FinanceSummary> {
    const s = await request<WireSummary>('/finance/summary');
    return {
      cameIn: { total: s.came_in.total, byAccount: s.came_in.by_account.map(fromWireAccountLine) },
      wentOut: { total: s.went_out.total, byAccount: s.went_out.by_account.map(fromWireAccountLine) },
      net: s.net,
      cash: s.cash,
      payable: s.payable,
    };
  },

  async ledger(filters: LedgerFilters = {}, page = 1): Promise<Paginated<LedgerEntry>> {
    const result = await request<Paginated<WireLedgerEntry>>('/finance/ledger', {
      query: { page, account: filters.account, event: filters.event, kind: filters.kind },
    });
    return { ...result, results: result.results.map(fromWireLedgerEntry) };
  },

  async reconcile(): Promise<Reconcile> {
    const r = await request<WireReconcile>('/finance/reconcile');
    return { ok: r.ok, checks: r.checks };
  },

  async trace(figure: string): Promise<Trace> {
    const t = await request<WireTrace>('/finance/trace', { query: { figure } });
    return {
      figure: t.figure,
      label: t.label,
      total: t.total,
      entryCount: t.entry_count,
      entries: t.entries.map((e) => ({
        id: e.id,
        postedAt: e.posted_at,
        description: e.description,
        kind: e.kind,
        amount: e.amount,
        lines: fromWireLines(e.lines),
        source: fromWireSource(e.source),
      })),
    };
  },
};
