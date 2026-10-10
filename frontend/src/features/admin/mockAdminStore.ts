import { ApiRequestError } from '../../api/client';
import { findUserById, getCurrentMockUser, updateUser } from '../auth/mockUsers';
import type { AuditLogItem, RoleAssignment, RoleAssignmentDraft } from './types';

type MockRoleAssignment = RoleAssignment;

const ROLES_KEY = 'campusleague.mock.roleAssignments';
const AUDIT_KEY = 'campusleague.mock.auditLog';

function seedRoles(): MockRoleAssignment[] {
  const today = new Date().toISOString().slice(0, 10);
  const addYears = (n: number) => new Date(Date.now() + n * 365 * 86_400_000).toISOString().slice(0, 10);
  return [
    { id: 1, user: 4, role: 'president', termStart: today, termEnd: addYears(1), createdAt: new Date().toISOString() },
    { id: 2, user: 5, role: 'treasurer', termStart: today, termEnd: addYears(1), createdAt: new Date().toISOString() },
    { id: 3, user: 6, role: 'event_manager', termStart: today, termEnd: addYears(1), createdAt: new Date().toISOString() },
  ];
}

function seedAudit(): AuditLogItem[] {
  const now = Date.now();
  return [
    {
      id: 1,
      actor: { id: 4, name: 'Pia President' },
      action: 'role.assigned',
      objectType: 'RoleAssignment',
      objectId: 2,
      before: null,
      after: { user: 5, role: 'treasurer' },
      at: new Date(now - 20 * 86_400_000).toISOString(),
    },
    {
      id: 2,
      actor: { id: 5, name: 'Tom Treasurer' },
      action: 'expense.approved',
      objectType: 'Expense',
      objectId: 1,
      before: { status: 'submitted' },
      after: { status: 'approved' },
      at: new Date(now - 17 * 86_400_000).toISOString(),
    },
    {
      id: 3,
      actor: { id: 6, name: 'Eva Events' },
      action: 'stock.restocked',
      objectType: 'ProductSize',
      objectId: 2,
      before: { stock: 3 },
      after: { stock: 10 },
      at: new Date(now - 12 * 86_400_000).toISOString(),
    },
    {
      id: 4,
      actor: { id: 6, name: 'Eva Events' },
      action: 'savefile.updated',
      objectType: 'SaveFile',
      objectId: 1,
      before: { what_worked: '' },
      after: { what_worked: 'QR check-in kept the queue short.' },
      at: new Date(now - 5 * 86_400_000).toISOString(),
    },
  ];
}

function loadRoles(): MockRoleAssignment[] {
  try {
    const raw = localStorage.getItem(ROLES_KEY);
    if (raw) return JSON.parse(raw) as MockRoleAssignment[];
  } catch {
    /* storage unavailable or corrupt */
  }
  const seeded = seedRoles();
  saveRoles(seeded);
  return seeded;
}

function saveRoles(items: MockRoleAssignment[]): void {
  try {
    localStorage.setItem(ROLES_KEY, JSON.stringify(items));
  } catch {
    /* storage unavailable */
  }
}

function loadAudit(): AuditLogItem[] {
  try {
    const raw = localStorage.getItem(AUDIT_KEY);
    if (raw) return JSON.parse(raw) as AuditLogItem[];
  } catch {
    /* storage unavailable or corrupt */
  }
  const seeded = seedAudit();
  saveAudit(seeded);
  return seeded;
}

function saveAudit(items: AuditLogItem[]): void {
  try {
    localStorage.setItem(AUDIT_KEY, JSON.stringify(items));
  } catch {
    /* storage unavailable */
  }
}

function appendAudit(entry: Omit<AuditLogItem, 'id' | 'at'>): void {
  const items = loadAudit();
  items.push({ ...entry, id: items.reduce((max, a) => Math.max(max, a.id), 0) + 1, at: new Date().toISOString() });
  saveAudit(items);
}

function requirePresident() {
  const user = getCurrentMockUser();
  if (!user) throw new ApiRequestError({ code: 'not_authenticated', message: 'No active session.' });
  if (!user.roles.includes('president')) {
    throw new ApiRequestError({ code: 'permission_denied', message: 'Only the president can do this.' });
  }
  return user;
}

export const mockAdmin = {
  listRoles(): RoleAssignment[] {
    requirePresident();
    return loadRoles().sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  },

  assignRole(draft: RoleAssignmentDraft): RoleAssignment {
    const actor = requirePresident();
    if (draft.termEnd < draft.termStart) {
      throw new ApiRequestError({ code: 'validation_error', message: 'Term end cannot be before term start.', field: 'term_end', errors: [{ field: 'term_end', code: 'term_end_before_start', message: 'Term end cannot be before term start.' }] });
    }
    const target = findUserById(draft.user);
    if (!target) throw new ApiRequestError({ code: 'validation_error', message: 'No such user.', field: 'user' });

    const items = loadRoles();
    const created: MockRoleAssignment = { id: items.reduce((max, r) => Math.max(max, r.id), 0) + 1, user: draft.user, role: draft.role, termStart: draft.termStart, termEnd: draft.termEnd, createdAt: new Date().toISOString() };
    items.push(created);
    saveRoles(items);

    // Reflects immediately in the mock's own User.roles (no per-role term
    // tracking on that object), so the rest of the app sees the new access
    // right away — a real backend derives roles from assignments + today's
    // date on every request instead.
    if (!target.roles.includes(draft.role)) {
      updateUser(target.email, { roles: [...target.roles, draft.role] });
    }

    appendAudit({ actor: { id: actor.id, name: actor.name }, action: 'role.assigned', objectType: 'RoleAssignment', objectId: created.id, before: null, after: { user: draft.user, role: draft.role } });

    return created;
  },

  listAuditLog(action?: string): AuditLogItem[] {
    requirePresident();
    return loadAudit()
      .filter((a) => !action || a.action === action)
      .sort((a, b) => b.at.localeCompare(a.at));
  },
};
