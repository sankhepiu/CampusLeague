export type FundraiserStatus = 'planned' | 'active' | 'closed';
export type TaskStatus = 'todo' | 'doing' | 'done';

export interface FundraiserProgress {
  goalAmount: number; // paise
  raisedAmount: number; // paise
  raisedPct: number; // capped at 100
  tasksTotal: number;
  tasksDone: number;
  onTrack: boolean;
}

export interface TaskAssignee {
  id: number;
  name: string;
  roleNote: string;
}

export interface Task {
  id: number;
  fundraiser: number | null;
  event: number | null;
  title: string;
  description: string;
  status: TaskStatus;
  dueDate: string | null;
  assignees: TaskAssignee[];
}

export interface Fundraiser {
  id: number;
  title: string;
  goalAmount: number; // paise
  startsOn: string;
  endsOn: string;
  status: FundraiserStatus;
  progress: FundraiserProgress;
  tasks: Task[];
}

export interface FundraiserDraft {
  title: string;
  goalAmount: number; // paise
  startsOn: string;
  endsOn: string;
  status?: FundraiserStatus;
}

export interface TaskDraft {
  fundraiser?: number;
  event?: number;
  title: string;
  description?: string;
  dueDate?: string | null;
}

export interface AssignRequest {
  user: number;
  roleNote: string;
}

export interface SaleRequest {
  amount: number; // paise
  note?: string;
}
