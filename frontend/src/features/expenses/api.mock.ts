import type { Paginated } from '../../api/client';
import { mockExpenses, toPublicExpense } from './mockExpensesStore';
import type { Expense, ExpenseStatus, ExpenseSubmission, ListExpensesParams } from './types';

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const PAGE_SIZE = 20;

function paginate(items: Expense[], page: number): Paginated<Expense> {
  const start = (page - 1) * PAGE_SIZE;
  const results = items.slice(start, start + PAGE_SIZE);
  return { count: items.length, next: start + PAGE_SIZE < items.length ? `?page=${page + 1}` : null, previous: page > 1 ? `?page=${page - 1}` : null, results };
}

export const mockExpensesApi = {
  async submit(submission: ExpenseSubmission): Promise<Expense> {
    await delay(500);
    return toPublicExpense(mockExpenses.submit(submission));
  },

  async listMine(page = 1): Promise<Paginated<Expense>> {
    await delay(300);
    return paginate(mockExpenses.listMine().map(toPublicExpense), page);
  },

  async listAll(params: ListExpensesParams = {}, page = 1): Promise<Paginated<Expense>> {
    await delay(300);
    return paginate(mockExpenses.listAll(params.status).map(toPublicExpense), page);
  },

  async approve(id: number, reason?: string): Promise<Expense> {
    await delay(400);
    return toPublicExpense(mockExpenses.decide(id, 'approved', reason));
  },

  async reject(id: number, reason: string): Promise<Expense> {
    await delay(400);
    return toPublicExpense(mockExpenses.decide(id, 'rejected', reason));
  },

  async markPaid(id: number): Promise<Expense> {
    await delay(350);
    return toPublicExpense(mockExpenses.markPaid(id));
  },
};

export type { ExpenseStatus };
