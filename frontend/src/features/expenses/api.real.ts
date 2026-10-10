import { request, type Paginated } from '../../api/client';
import type { Approval, Expense, ExpenseCategory, ExpenseStatus, ExpenseSubmission, ListExpensesParams } from './types';

interface WireApproval {
  decision: Approval['decision'];
  reason: string | null;
  decided_at: string;
  approver: { id: number; name: string };
}

interface WireExpense {
  id: number;
  requester: { id: number; name: string };
  amount: number;
  category: ExpenseCategory;
  event: number | null;
  fundraiser: number | null;
  description: string;
  receipt_url: string;
  status: ExpenseStatus;
  created_at: string;
  approval: WireApproval | null;
}

function fromWireExpense(e: WireExpense): Expense {
  return {
    id: e.id,
    requester: e.requester,
    amount: e.amount,
    category: e.category,
    event: e.event,
    fundraiser: e.fundraiser,
    description: e.description,
    receiptUrl: e.receipt_url,
    status: e.status,
    createdAt: e.created_at,
    approval: e.approval
      ? { decision: e.approval.decision, reason: e.approval.reason, decidedAt: e.approval.decided_at, approver: e.approval.approver }
      : null,
  };
}

export const realExpensesApi = {
  async submit(submission: ExpenseSubmission): Promise<Expense> {
    const form = new FormData();
    form.set('amount', String(submission.amountPaise));
    form.set('category', submission.category);
    form.set('description', submission.description);
    form.set('receipt_file', submission.receiptFile);
    if (submission.event !== undefined) form.set('event', String(submission.event));
    if (submission.fundraiser !== undefined) form.set('fundraiser', String(submission.fundraiser));
    return fromWireExpense(await request<WireExpense>('/expenses', { method: 'POST', body: form }));
  },

  async listMine(page = 1): Promise<Paginated<Expense>> {
    const result = await request<Paginated<WireExpense>>('/expenses/me', { query: { page } });
    return { ...result, results: result.results.map(fromWireExpense) };
  },

  async listAll(params: ListExpensesParams = {}, page = 1): Promise<Paginated<Expense>> {
    const result = await request<Paginated<WireExpense>>('/expenses', { query: { page, status: params.status } });
    return { ...result, results: result.results.map(fromWireExpense) };
  },

  async approve(id: number, reason?: string): Promise<Expense> {
    return fromWireExpense(await request<WireExpense>(`/expenses/${id}/approve`, { method: 'POST', body: reason ? { reason } : {} }));
  },

  async reject(id: number, reason: string): Promise<Expense> {
    return fromWireExpense(await request<WireExpense>(`/expenses/${id}/reject`, { method: 'POST', body: { reason } }));
  },

  async markPaid(id: number): Promise<Expense> {
    return fromWireExpense(await request<WireExpense>(`/expenses/${id}/mark-paid`, { method: 'POST' }));
  },
};
