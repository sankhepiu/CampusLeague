import { session } from '../../api/client';
import type { AuthUser } from './types';

export const MOCK_TOKEN_PREFIX = 'mock-token::';

/** Single localStorage-backed mock "users table" shared by the auth mock and
 * the membership mock, so buying a plan (membership mock) is reflected in
 * /auth/me (auth mock) within the same session. Mirrors the real Django
 * backend's eventual source of truth; swapping VITE_USE_MOCK_API=false drops
 * this entirely in favor of the real API. */

const SEED_USERS: AuthUser[] = [
  {
    id: 1,
    email: 'newmember@campusleague.dev',
    name: 'Nina New',
    collegeId: 'SSA-101',
    phone: '',
    roles: [],
    membershipStatus: 'none',
  },
  {
    id: 2,
    email: 'active@campusleague.dev',
    name: 'Amit Active',
    collegeId: 'SSA-102',
    phone: '',
    roles: [],
    membershipStatus: 'active',
  },
  {
    id: 3,
    email: 'lapsed@campusleague.dev',
    name: 'Lara Lapsed',
    collegeId: 'SSA-103',
    phone: '',
    roles: [],
    membershipStatus: 'lapsed',
  },
  {
    id: 4,
    email: 'president@campusleague.dev',
    name: 'Pia President',
    collegeId: 'SSA-010',
    phone: '',
    roles: ['president'],
    membershipStatus: 'active',
  },
  {
    id: 5,
    email: 'treasurer@campusleague.dev',
    name: 'Tom Treasurer',
    collegeId: 'SSA-011',
    phone: '',
    roles: ['treasurer'],
    membershipStatus: 'active',
  },
  {
    id: 6,
    email: 'eventmanager@campusleague.dev',
    name: 'Eva Events',
    collegeId: 'SSA-012',
    phone: '',
    roles: ['event_manager'],
    membershipStatus: 'active',
  },
];

const STORE_KEY = 'campusleague.mock.users';

function loadStore(): Record<string, AuthUser> {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) return JSON.parse(raw) as Record<string, AuthUser>;
  } catch {
    /* storage unavailable or corrupt — fall through to reseed */
  }
  const seeded = Object.fromEntries(SEED_USERS.map((u) => [u.email, u]));
  saveStore(seeded);
  return seeded;
}

function saveStore(store: Record<string, AuthUser>): void {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(store));
  } catch {
    /* storage unavailable */
  }
}

export function findUserByEmail(email: string): AuthUser | undefined {
  return loadStore()[email.trim().toLowerCase()];
}

export function findUserById(id: number): AuthUser | undefined {
  return Object.values(loadStore()).find((u) => u.id === id);
}

/** Every mock user (seed demo accounts + anyone who has signed up this
 * session) — backs the staff members-list mock. */
export function listAllUsers(): AuthUser[] {
  return Object.values(loadStore());
}

export function createUser(user: Omit<AuthUser, 'id'>): AuthUser {
  const store = loadStore();
  const maxId = Object.values(store).reduce((max, u) => Math.max(max, u.id), 999);
  const created: AuthUser = { ...user, id: maxId + 1 };
  store[created.email] = created;
  saveStore(store);
  return created;
}

/** The signed-in mock user, resolved from the session token — the one piece
 * every other mock module (membership, staff list) needs to act "as" the
 * current user. Mirrors what the real backend derives from the auth token. */
export function getCurrentMockUser(): AuthUser | undefined {
  const token = session.getToken();
  if (!token?.startsWith(MOCK_TOKEN_PREFIX)) return undefined;
  return findUserById(Number(token.slice(MOCK_TOKEN_PREFIX.length)));
}

export function updateUser(email: string, patch: Partial<AuthUser>): AuthUser {
  const store = loadStore();
  const existing = store[email.trim().toLowerCase()];
  if (!existing) throw new Error(`mock user not found: ${email}`);
  const updated = { ...existing, ...patch };
  store[updated.email] = updated;
  saveStore(store);
  return updated;
}

/** The fixed seed list for the login page's quick-fill demo buttons — always
 * the original six, regardless of how many accounts have since signed up. */
export const DEMO_ACCOUNT_EMAILS = SEED_USERS.map((u) => u.email);

const ROLE_LABEL: Record<string, string> = {
  president: 'President',
  treasurer: 'Treasurer',
  event_manager: 'Event Manager',
  volunteer_coordinator: 'Volunteer Coordinator',
  member: 'Member',
};

const STATUS_LABEL: Record<AuthUser['membershipStatus'], string> = {
  none: 'No plan yet',
  active: 'Active member',
  lapsed: 'Lapsed member',
};

/** Friendly one-line label for a demo-account quick-fill button, since an
 * ordinary user's `roles` is empty — membership status is the meaningful
 * thing to show them instead. */
export function demoAccountLabel(user: AuthUser): string {
  return user.roles[0] ? ROLE_LABEL[user.roles[0]] : STATUS_LABEL[user.membershipStatus];
}
