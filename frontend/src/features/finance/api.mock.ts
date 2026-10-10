import { ApiRequestError, type Paginated } from '../../api/client';
import { getCurrentMockUser } from '../auth/mockUsers';
import { computeReconcile, computeSummary, listLedger, trace as traceFigure } from './financeLedgerEngine';
import type { FinanceSummary, LedgerEntry, LedgerFilters, Reconcile, Trace } from './types';

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const PAGE_SIZE = 20;
const FINANCE_ROLES = ['president', 'treasurer'];

function requireFinanceRole(): void {
  const user = getCurrentMockUser();
  if (!user) throw new ApiRequestError({ code: 'not_authenticated', message: 'No active session.' });
  if (!user.roles.some((r) => FINANCE_ROLES.includes(r))) {
    throw new ApiRequestError({ code: 'permission_denied', message: 'Only the president or treasurer can view finance.' });
  }
}

export const mockFinanceApi = {
  async summary(): Promise<FinanceSummary> {
    requireFinanceRole();
    await delay(300);
    return computeSummary();
  },

  async ledger(filters: LedgerFilters = {}, page = 1): Promise<Paginated<LedgerEntry>> {
    requireFinanceRole();
    await delay(300);
    const { count, results } = listLedger(filters, page, PAGE_SIZE);
    const start = (page - 1) * PAGE_SIZE;
    return {
      count,
      next: start + PAGE_SIZE < count ? `?page=${page + 1}` : null,
      previous: page > 1 ? `?page=${page - 1}` : null,
      results,
    };
  },

  async reconcile(): Promise<Reconcile> {
    requireFinanceRole();
    await delay(300);
    return computeReconcile();
  },

  async trace(figure: string): Promise<Trace> {
    requireFinanceRole();
    await delay(300);
    return traceFigure(figure);
  },
};
