import { request, type Paginated } from '../../api/client';
import type { AssignRequest, Fundraiser, FundraiserDraft, FundraiserStatus, SaleRequest, Task, TaskDraft, TaskStatus } from './types';

interface WireAssignee {
  id: number;
  name: string;
  role_note: string;
}

interface WireTask {
  id: number;
  fundraiser: number | null;
  event: number | null;
  title: string;
  description: string;
  status: TaskStatus;
  due_date: string | null;
  assignees: WireAssignee[];
}

interface WireProgress {
  goal_amount: number;
  raised_amount: number;
  raised_pct: number;
  tasks_total: number;
  tasks_done: number;
  on_track: boolean;
}

interface WireFundraiser {
  id: number;
  title: string;
  goal_amount: number;
  starts_on: string;
  ends_on: string;
  status: FundraiserStatus;
  progress: WireProgress;
  tasks: WireTask[];
}

function fromWireTask(t: WireTask): Task {
  return {
    id: t.id,
    fundraiser: t.fundraiser,
    event: t.event,
    title: t.title,
    description: t.description,
    status: t.status,
    dueDate: t.due_date,
    assignees: t.assignees.map((a) => ({ id: a.id, name: a.name, roleNote: a.role_note })),
  };
}

function fromWireFundraiser(f: WireFundraiser): Fundraiser {
  return {
    id: f.id,
    title: f.title,
    goalAmount: f.goal_amount,
    startsOn: f.starts_on,
    endsOn: f.ends_on,
    status: f.status,
    progress: {
      goalAmount: f.progress.goal_amount,
      raisedAmount: f.progress.raised_amount,
      raisedPct: f.progress.raised_pct,
      tasksTotal: f.progress.tasks_total,
      tasksDone: f.progress.tasks_done,
      onTrack: f.progress.on_track,
    },
    tasks: f.tasks.map(fromWireTask),
  };
}

export const realVolunteeringApi = {
  async listFundraisers(page = 1): Promise<Paginated<Fundraiser>> {
    const result = await request<Paginated<WireFundraiser>>('/fundraisers', { query: { page } });
    return { ...result, results: result.results.map(fromWireFundraiser) };
  },

  async getFundraiser(id: number): Promise<Fundraiser> {
    return fromWireFundraiser(await request<WireFundraiser>(`/fundraisers/${id}`));
  },

  async createFundraiser(draft: FundraiserDraft): Promise<Fundraiser> {
    return fromWireFundraiser(
      await request<WireFundraiser>('/fundraisers', {
        method: 'POST',
        body: { title: draft.title, goal_amount: draft.goalAmount, starts_on: draft.startsOn, ends_on: draft.endsOn, ...(draft.status ? { status: draft.status } : {}) },
      }),
    );
  },

  async updateFundraiser(id: number, draft: Partial<FundraiserDraft>): Promise<Fundraiser> {
    const body: Record<string, unknown> = {};
    if (draft.title !== undefined) body.title = draft.title;
    if (draft.goalAmount !== undefined) body.goal_amount = draft.goalAmount;
    if (draft.startsOn !== undefined) body.starts_on = draft.startsOn;
    if (draft.endsOn !== undefined) body.ends_on = draft.endsOn;
    if (draft.status !== undefined) body.status = draft.status;
    return fromWireFundraiser(await request<WireFundraiser>(`/fundraisers/${id}`, { method: 'PATCH', body }));
  },

  async recordSale(fundraiserId: number, { amount, note }: SaleRequest): Promise<Fundraiser> {
    return fromWireFundraiser(
      await request<WireFundraiser>(`/fundraisers/${fundraiserId}/sales`, { method: 'POST', body: { amount, ...(note ? { note } : {}) } }),
    );
  },

  async createTask(draft: TaskDraft): Promise<Task> {
    return fromWireTask(
      await request<WireTask>('/tasks', {
        method: 'POST',
        body: {
          ...(draft.fundraiser !== undefined ? { fundraiser: draft.fundraiser } : {}),
          ...(draft.event !== undefined ? { event: draft.event } : {}),
          title: draft.title,
          ...(draft.description !== undefined ? { description: draft.description } : {}),
          ...(draft.dueDate !== undefined ? { due_date: draft.dueDate } : {}),
        },
      }),
    );
  },

  async updateTask(id: number, draft: Partial<TaskDraft>): Promise<Task> {
    const body: Record<string, unknown> = {};
    if (draft.fundraiser !== undefined) body.fundraiser = draft.fundraiser;
    if (draft.event !== undefined) body.event = draft.event;
    if (draft.title !== undefined) body.title = draft.title;
    if (draft.description !== undefined) body.description = draft.description;
    if (draft.dueDate !== undefined) body.due_date = draft.dueDate;
    return fromWireTask(await request<WireTask>(`/tasks/${id}`, { method: 'PATCH', body }));
  },

  async assignTask(id: number, { user, roleNote }: AssignRequest): Promise<Task> {
    return fromWireTask(await request<WireTask>(`/tasks/${id}/assign`, { method: 'POST', body: { user, role_note: roleNote } }));
  },

  async setTaskStatus(id: number, status: TaskStatus): Promise<Task> {
    return fromWireTask(await request<WireTask>(`/tasks/${id}/status`, { method: 'PATCH', body: { status } }));
  },
};
