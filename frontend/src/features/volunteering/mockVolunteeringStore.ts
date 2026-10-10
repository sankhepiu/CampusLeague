import { ApiRequestError } from '../../api/client';
import { findUserById, getCurrentMockUser } from '../auth/mockUsers';
import type { AssignRequest, Fundraiser, FundraiserDraft, FundraiserStatus, SaleRequest, Task, TaskDraft, TaskStatus } from './types';

interface MockAssignee {
  id: number;
  name: string;
  roleNote: string;
}

interface MockTask {
  id: number;
  fundraiser: number | null;
  event: number | null;
  title: string;
  description: string;
  status: TaskStatus;
  dueDate: string | null;
  assignees: MockAssignee[];
}

interface MockSale {
  id: number;
  fundraiserId: number;
  amount: number;
  note: string;
  recordedAt: string;
}

interface MockFundraiser {
  id: number;
  title: string;
  goalAmount: number;
  startsOn: string;
  endsOn: string;
  status: FundraiserStatus;
}

interface MockVolunteeringState {
  fundraisers: MockFundraiser[];
  tasks: MockTask[];
  sales: MockSale[];
}

const STORE_KEY = 'campusleague.mock.volunteering';
const isoDate = (daysFromNow: number) => new Date(Date.now() + daysFromNow * 86_400_000).toISOString().slice(0, 10);

function seed(): MockVolunteeringState {
  return {
    fundraisers: [
      { id: 1, title: 'Spring Carnival Fund', goalAmount: 500000, startsOn: isoDate(-10), endsOn: isoDate(20), status: 'active' },
      { id: 2, title: 'Library Drive', goalAmount: 300000, startsOn: isoDate(-30), endsOn: isoDate(5), status: 'active' },
    ],
    tasks: [
      { id: 1, fundraiser: 1, event: null, title: 'Book venue', description: 'Confirm the quad booking with facilities.', status: 'done', dueDate: isoDate(-5), assignees: [{ id: 4, name: 'Pia President', roleNote: 'Lead organizer' }] },
      {
        id: 2,
        fundraiser: 1,
        event: null,
        title: 'Design posters',
        description: 'Draft artwork for the carnival posters.',
        status: 'doing',
        dueDate: isoDate(3),
        assignees: [{ id: 2, name: 'Amit Active', roleNote: 'Designer' }],
      },
      { id: 3, fundraiser: 1, event: null, title: 'Sell tickets at gate', description: '', status: 'todo', dueDate: isoDate(18), assignees: [] },
      { id: 4, fundraiser: 2, event: null, title: 'Collect pledges', description: 'Door-to-door pledge drive in the dorms.', status: 'todo', dueDate: isoDate(2), assignees: [] },
    ],
    sales: [
      { id: 1, fundraiserId: 1, amount: 200000, note: 'Bake sale weekend 1', recordedAt: new Date(Date.now() - 3 * 86_400_000).toISOString() },
      { id: 2, fundraiserId: 2, amount: 50000, note: 'Pledge drive week 1', recordedAt: new Date(Date.now() - 10 * 86_400_000).toISOString() },
    ],
  };
}

function loadState(): MockVolunteeringState {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) return JSON.parse(raw) as MockVolunteeringState;
  } catch {
    /* storage unavailable or corrupt */
  }
  const seeded = seed();
  saveState(seeded);
  return seeded;
}

function saveState(state: MockVolunteeringState): void {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(state));
  } catch {
    /* storage unavailable */
  }
}

function nextId(ids: number[]): number {
  return ids.reduce((max, id) => Math.max(max, id), 0) + 1;
}

function raisedAmountFor(state: MockVolunteeringState, fundraiserId: number): number {
  return state.sales.filter((s) => s.fundraiserId === fundraiserId).reduce((sum, s) => sum + s.amount, 0);
}

/** "on_track" per the contract's own assumption: the share of the goal
 * raised is at least the share of the time elapsed. */
function onTrackFor(fundraiser: MockFundraiser, raisedAmount: number): boolean {
  const start = new Date(fundraiser.startsOn).getTime();
  const end = new Date(fundraiser.endsOn).getTime();
  const now = Date.now();
  const totalSpan = end - start;
  if (totalSpan <= 0) return raisedAmount >= fundraiser.goalAmount;
  const elapsedPct = Math.min(1, Math.max(0, (now - start) / totalSpan));
  const raisedPct = fundraiser.goalAmount > 0 ? raisedAmount / fundraiser.goalAmount : 1;
  return raisedPct >= elapsedPct;
}

export function toPublicFundraiser(state: MockVolunteeringState, f: MockFundraiser): Fundraiser {
  const tasks = state.tasks.filter((t) => t.fundraiser === f.id);
  const raisedAmount = raisedAmountFor(state, f.id);
  const raisedPct = f.goalAmount > 0 ? Math.min(100, Math.round((raisedAmount / f.goalAmount) * 1000) / 10) : 0;
  return {
    id: f.id,
    title: f.title,
    goalAmount: f.goalAmount,
    startsOn: f.startsOn,
    endsOn: f.endsOn,
    status: f.status,
    progress: {
      goalAmount: f.goalAmount,
      raisedAmount,
      raisedPct,
      tasksTotal: tasks.length,
      tasksDone: tasks.filter((t) => t.status === 'done').length,
      onTrack: onTrackFor(f, raisedAmount),
    },
    tasks: tasks.map(toPublicTask),
  };
}

function toPublicTask(t: MockTask): Task {
  return { ...t, assignees: t.assignees.map((a) => ({ ...a })) };
}

function requireUser() {
  const user = getCurrentMockUser();
  if (!user) throw new ApiRequestError({ code: 'not_authenticated', message: 'No active session.' });
  return user;
}

const VOLUNTEER_ADMIN_ROLES = ['president', 'volunteer_coordinator'];
function requireVolunteerAdmin() {
  const user = requireUser();
  if (!user.roles.some((r) => VOLUNTEER_ADMIN_ROLES.includes(r))) {
    throw new ApiRequestError({ code: 'permission_denied', message: 'Only the president or volunteer coordinator can do this.' });
  }
  return user;
}

export const mockVolunteering = {
  listFundraisers(): Fundraiser[] {
    const state = loadState();
    return state.fundraisers.map((f) => toPublicFundraiser(state, f));
  },

  getFundraiser(id: number): Fundraiser {
    const state = loadState();
    const f = state.fundraisers.find((x) => x.id === id);
    if (!f) throw new ApiRequestError({ code: 'not_found', message: 'No such fundraiser.' });
    return toPublicFundraiser(state, f);
  },

  createFundraiser(draft: FundraiserDraft): Fundraiser {
    requireVolunteerAdmin();
    if (draft.endsOn <= draft.startsOn) {
      throw new ApiRequestError({ code: 'validation_error', message: 'Fundraiser must end after it starts.', field: 'ends_on' });
    }
    const state = loadState();
    const f: MockFundraiser = {
      id: nextId(state.fundraisers.map((x) => x.id)),
      title: draft.title,
      goalAmount: draft.goalAmount,
      startsOn: draft.startsOn,
      endsOn: draft.endsOn,
      status: draft.status ?? 'planned',
    };
    state.fundraisers.push(f);
    saveState(state);
    return toPublicFundraiser(state, f);
  },

  updateFundraiser(id: number, patch: Partial<FundraiserDraft>): Fundraiser {
    requireVolunteerAdmin();
    const state = loadState();
    const f = state.fundraisers.find((x) => x.id === id);
    if (!f) throw new ApiRequestError({ code: 'not_found', message: 'No such fundraiser.' });
    const nextStart = patch.startsOn ?? f.startsOn;
    const nextEnd = patch.endsOn ?? f.endsOn;
    if (nextEnd <= nextStart) {
      throw new ApiRequestError({ code: 'validation_error', message: 'Fundraiser must end after it starts.', field: 'ends_on' });
    }
    Object.assign(f, { title: patch.title ?? f.title, goalAmount: patch.goalAmount ?? f.goalAmount, startsOn: nextStart, endsOn: nextEnd, status: patch.status ?? f.status });
    saveState(state);
    return toPublicFundraiser(state, f);
  },

  recordSale(fundraiserId: number, { amount, note }: SaleRequest): Fundraiser {
    requireVolunteerAdmin();
    const state = loadState();
    const f = state.fundraisers.find((x) => x.id === fundraiserId);
    if (!f) throw new ApiRequestError({ code: 'not_found', message: 'No such fundraiser.' });
    if (amount <= 0) throw new ApiRequestError({ code: 'validation_error', message: 'Amount must be greater than zero.', field: 'amount' });
    state.sales.push({ id: nextId(state.sales.map((s) => s.id)), fundraiserId, amount, note: note ?? '', recordedAt: new Date().toISOString() });
    saveState(state);
    return toPublicFundraiser(state, f);
  },

  createTask(draft: TaskDraft): Task {
    requireVolunteerAdmin();
    if (!draft.fundraiser && !draft.event) {
      throw new ApiRequestError({ code: 'validation_error', message: 'A task needs a fundraiser or an event.', field: 'fundraiser' });
    }
    const state = loadState();
    const task: MockTask = {
      id: nextId(state.tasks.map((t) => t.id)),
      fundraiser: draft.fundraiser ?? null,
      event: draft.event ?? null,
      title: draft.title,
      description: draft.description ?? '',
      status: 'todo',
      dueDate: draft.dueDate ?? null,
      assignees: [],
    };
    state.tasks.push(task);
    saveState(state);
    return toPublicTask(task);
  },

  updateTask(id: number, patch: Partial<TaskDraft>): Task {
    requireVolunteerAdmin();
    const state = loadState();
    const task = state.tasks.find((t) => t.id === id);
    if (!task) throw new ApiRequestError({ code: 'not_found', message: 'No such task.' });
    Object.assign(task, {
      title: patch.title ?? task.title,
      description: patch.description ?? task.description,
      dueDate: patch.dueDate !== undefined ? patch.dueDate : task.dueDate,
      fundraiser: patch.fundraiser !== undefined ? patch.fundraiser : task.fundraiser,
      event: patch.event !== undefined ? patch.event : task.event,
    });
    saveState(state);
    return toPublicTask(task);
  },

  assignTask(id: number, { user, roleNote }: AssignRequest): Task {
    requireVolunteerAdmin();
    const state = loadState();
    const task = state.tasks.find((t) => t.id === id);
    if (!task) throw new ApiRequestError({ code: 'not_found', message: 'No such task.' });
    const person = findUserById(user);
    if (!person) throw new ApiRequestError({ code: 'validation_error', message: 'Unknown user.', field: 'user' });
    const existing = task.assignees.find((a) => a.id === user);
    if (existing) {
      existing.roleNote = roleNote;
    } else {
      task.assignees.push({ id: person.id, name: person.name, roleNote });
    }
    saveState(state);
    return toPublicTask(task);
  },

  setTaskStatus(id: number, status: TaskStatus): Task {
    const user = requireUser();
    const state = loadState();
    const task = state.tasks.find((t) => t.id === id);
    if (!task) throw new ApiRequestError({ code: 'not_found', message: 'No such task.' });

    const isStaff = user.roles.some((r) => VOLUNTEER_ADMIN_ROLES.includes(r));
    const isAssignee = task.assignees.some((a) => a.id === user.id);
    if (!isStaff && !isAssignee) {
      throw new ApiRequestError({ code: 'permission_denied', message: 'You can only update tasks you are assigned to.' });
    }

    task.status = status;
    saveState(state);
    return toPublicTask(task);
  },
};

export interface MockFundraiserSale {
  id: number;
  fundraiserId: number;
  fundraiserTitle: string;
  amount: number;
  note: string;
  recordedAt: string;
}

/** Every recorded sale across every fundraiser, with the fundraiser's title
 * resolved — the finance ledger mock needs this to derive fundraiser_sale
 * entries; the public Fundraiser type only exposes the aggregated total. */
export function listAllMockFundraiserSales(): MockFundraiserSale[] {
  const state = loadState();
  const titleById = new Map(state.fundraisers.map((f) => [f.id, f.title]));
  return state.sales.map((s) => ({
    id: s.id,
    fundraiserId: s.fundraiserId,
    fundraiserTitle: titleById.get(s.fundraiserId) ?? `Fundraiser #${s.fundraiserId}`,
    amount: s.amount,
    note: s.note,
    recordedAt: s.recordedAt,
  }));
}
