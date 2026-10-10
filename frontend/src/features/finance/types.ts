export type LedgerKind = 'membership_dues' | 'ticket_sale' | 'merch_sale' | 'fundraiser_sale' | 'expense_approved' | 'expense_paid';

export interface AccountLine {
  code: string;
  name: string;
  amount: number; // paise
}

export interface FigureTotal {
  total: number; // paise
  byAccount: AccountLine[];
}

export interface FinanceSummary {
  cameIn: FigureTotal;
  wentOut: FigureTotal;
  net: number; // paise
  cash: number; // paise
  payable: number; // paise
}

export interface LedgerAccount {
  code: string;
  name: string;
  type: 'asset' | 'liability' | 'revenue' | 'expense';
}

export interface LedgerLine {
  id: number;
  account: LedgerAccount;
  debit: number; // paise
  credit: number; // paise
}

export interface LedgerEntry {
  id: number;
  postedAt: string;
  description: string;
  sourceType: TraceSourceType;
  sourceId: number;
  kind: LedgerKind;
  event: number | null;
  reverses: number | null;
  lines: LedgerLine[];
}

export interface LedgerFilters {
  account?: string;
  event?: number;
  kind?: LedgerKind;
}

export interface ReconcileCheck {
  name: string;
  ok: boolean;
  expected: number;
  actual: number;
}

export interface Reconcile {
  ok: boolean;
  checks: ReconcileCheck[];
}

export type TraceSourceType = 'payment' | 'order_line' | 'order' | 'expense_request' | 'fundraiser_sale';

export interface TraceTicketDetail {
  type: 'ticket';
  id: number;
  code: string;
  holder: string;
  pricePaid: number;
  status: string;
  checkedInAt: string | null;
}

export interface TraceOrderLineDetails {
  order: number;
  buyer: string;
  tickets: TraceTicketDetail[];
}

export interface TraceMerchItem {
  product: string;
  size: string;
  qty: number;
  unitPrice: number;
}

export interface TraceOrderDetails {
  // GAP: the live backend doesn't send `order` on a merch order source yet
  // (teammate is adding it) — optional until then, not force-unwrapped.
  order?: number;
  buyer: string;
  items: TraceMerchItem[];
}

export interface TracePaymentDetails {
  payer: string;
  plan: string;
}

export interface TraceExpenseDetails {
  requester: string;
  // GAP: the live backend doesn't send `description`/`approved_by` on an
  // expense_request source yet (teammate is adding it) — optional until
  // then; CoinTrail renders a dash rather than "undefined" for these.
  description?: string;
  receiptUrl: string;
  approvedBy?: string | null;
}

export interface TraceFundraiserSaleDetails {
  fundraiser: string;
  note: string;
}

// A discriminated union (not type + a separate details union) so narrowing
// on `source.type` also narrows `source.details` to the matching shape.
export type TraceSource =
  | { type: 'order_line'; id: number; label: string; details: TraceOrderLineDetails }
  | { type: 'order'; id: number; label: string; details: TraceOrderDetails }
  | { type: 'payment'; id: number; label: string; details: TracePaymentDetails }
  | { type: 'expense_request'; id: number; label: string; details: TraceExpenseDetails }
  | { type: 'fundraiser_sale'; id: number; label: string; details: TraceFundraiserSaleDetails };

export interface TraceEntry {
  id: number;
  postedAt: string;
  description: string;
  kind: LedgerKind;
  amount: number; // paise, signed — negative for expenses inside a profit figure
  lines: LedgerLine[];
  source: TraceSource;
}

export interface Trace {
  figure: string;
  label: string;
  total: number; // paise
  entryCount: number;
  entries: TraceEntry[]; // capped at 200, newest first
}
