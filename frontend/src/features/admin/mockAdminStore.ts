import { ApiRequestError } from '../../api/client';
import { findUserById, getCurrentMockUser, updateUser } from '../auth/mockUsers';
import type { Role } from '../../core/config/roles';
import type { AuditLogItem, RoleAssignment } from './types';

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

/** Used by the roles feature's mock invite flow — an accepted invite creates
 * the role assignment itself, the same way `assignRole` below used to before
 * the invite step existed. Not president-gated here: the caller (accepting
 * the invite) already did its own "is this the nominee" check. */
export function addMockRoleAssignment(userId: number, role: Role, termStart: string, termEnd: string): RoleAssignment {
  const items = loadRoles();
  const created: MockRoleAssignment = { id: items.reduce((max, r) => Math.max(max, r.id), 0) + 1, user: userId, role, termStart, termEnd, createdAt: new Date().toISOString() };
  items.push(created);
  saveRoles(items);

  const target = findUserById(userId);
  if (target && !target.roles.includes(role)) {
    updateUser(target.email, { roles: [...target.roles, role] });
  }
  return created;
}

/** Ends every current (not-yet-ended) assignment of `role` for `userId` by
 * backdating its term — used when the roles feature ends an assignment. */
export function endMockRoleAssignment(userId: number, role: Role): RoleAssignment | null {
  const items = loadRoles();
  const today = new Date().toISOString().slice(0, 10);
  const yesterday = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);
  const current = items.find((r) => r.user === userId && r.role === role && r.termEnd >= today);
  if (!current) return null;

  if (current.termStart === today) {
    saveRoles(items.filter((r) => r.id !== current.id));
  } else {
    current.termEnd = yesterday;
    saveRoles(items);
  }

  const target = findUserById(userId);
  // Only drop the role from the user's live roles if they hold no other
  // current assignment of it (the mock doesn't model multiple concurrent
  // terms of the same role, so in practice this always clears it).
  if (target) {
    const stillHolds = loadRoles().some((r) => r.user === userId && r.role === role && r.termEnd >= today);
    if (!stillHolds) updateUser(target.email, { roles: target.roles.filter((r) => r !== role) });
  }
  return current.termStart === today ? null : { ...current, termEnd: yesterday };
}

export function findMockRoleAssignment(id: number): RoleAssignment | undefined {
  return loadRoles().find((r) => r.id === id);
}

export function currentRoleHoldersCount(role: Role): number {
  const today = new Date().toISOString().slice(0, 10);
  return loadRoles().filter((r) => r.role === role && r.termStart <= today && r.termEnd >= today).length;
}

export { appendAudit as appendMockAudit };

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

  listAuditLog(action?: string): AuditLogItem[] {
    requirePresident();
    return loadAudit()
      .filter((a) => !action || a.action === action)
      .sort((a, b) => b.at.localeCompare(a.at));
  },
};
