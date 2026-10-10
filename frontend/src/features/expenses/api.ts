import { env } from '../../core/config/env';
import { mockExpensesApi } from './api.mock';
import { realExpensesApi } from './api.real';

/** Same typed surface regardless of mode — components never branch on env.useMockApi. */
export const expensesApi = env.useMockApi ? mockExpensesApi : realExpensesApi;

export type { Approval, Expense, ExpenseCategory, ExpenseStatus, ExpenseSubmission, ListExpensesParams } from './types';
