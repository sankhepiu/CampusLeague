import { env } from '../../core/config/env';
import { mockFinanceApi } from './api.mock';
import { realFinanceApi } from './api.real';

/** Same typed surface regardless of mode — components never branch on env.useMockApi. */
export const financeApi = env.useMockApi ? mockFinanceApi : realFinanceApi;

export type {
  AccountLine,
  FinanceSummary,
  LedgerAccount,
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
