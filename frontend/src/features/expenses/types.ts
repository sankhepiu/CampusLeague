export type ExpenseCategory = 'event' | 'fundraiser' | 'general';
export type ExpenseStatus = 'submitted' | 'approved' | 'rejected' | 'paid';
export type ApprovalDecision = 'approved' | 'rejected';

export interface Approval {
  decision: ApprovalDecision;
  reason: string | null;
  decidedAt: string;
  approver: { id: number; name: string };
}

export interface Expense {
  id: number;
  requester: { id: number; name: string };
  amount: number; // paise
  category: ExpenseCategory;
  event: number | null;
  fundraiser: number | null;
  description: string;
  receiptUrl: string;
  status: ExpenseStatus;
  createdAt: string;
  approval: Approval | null;
}

export interface ExpenseSubmission {
  amountPaise: number;
  category: ExpenseCategory;
  description: string;
  receiptFile: File;
  event?: number;
  fundraiser?: number;
}

export interface ListExpensesParams {
  status?: ExpenseStatus;
}
