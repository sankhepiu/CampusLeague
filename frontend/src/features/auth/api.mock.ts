import { ApiRequestError, session } from '../../api/client';
import type { AuthUser, LoginRequest, SignupRequest } from './types';

/** Deterministic demo accounts so manual testers can switch roles without a backend.
 * Any password is accepted in mock mode. */
const MOCK_USERS: Record<string, AuthUser> = {
  'member@campusleague.dev': {
    id: 'user-member-1',
    name: 'Mia Member',
    email: 'member@campusleague.dev',
    roles: ['member'],
  },
  'organizer@campusleague.dev': {
    id: 'user-organizer-1',
    name: 'Omar Organizer',
    email: 'organizer@campusleague.dev',
    roles: ['organizer', 'member'],
  },
  'admin@campusleague.dev': {
    id: 'user-admin-1',
    name: 'Ada Admin',
    email: 'admin@campusleague.dev',
    roles: ['admin', 'organizer', 'member'],
  },
};

// Accounts created through the mock "Sign up" form, persisted so a refresh
// doesn't lose them. Separate from MOCK_USERS so the three demo accounts
// above always stay pristine/resettable.
const SIGNUPS_KEY = 'campusleague.mock.signups';

function loadSignedUpUsers(): Record<string, AuthUser> {
  try {
    const raw = localStorage.getItem(SIGNUPS_KEY);
    return raw ? (JSON.parse(raw) as Record<string, AuthUser>) : {};
  } catch {
    return {};
  }
}

function saveSignedUpUser(user: AuthUser): void {
  try {
    const all = loadSignedUpUsers();
    all[user.email] = user;
    localStorage.setItem(SIGNUPS_KEY, JSON.stringify(all));
  } catch {
    /* storage unavailable */
  }
}

function findUserByEmail(email: string): AuthUser | undefined {
  const key = email.trim().toLowerCase();
  return MOCK_USERS[key] ?? loadSignedUpUsers()[key];
}

function findUserById(id: string): AuthUser | undefined {
  return (
    Object.values(MOCK_USERS).find((u) => u.id === id) ??
    Object.values(loadSignedUpUsers()).find((u) => u.id === id)
  );
}

const MOCK_TOKEN_PREFIX = 'mock-token::';
const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
let signupCounter = 0;

export const mockAuthApi = {
  async login({ email }: LoginRequest): Promise<AuthUser> {
    await delay(400);
    const user = findUserByEmail(email);
    if (!user) {
      throw new ApiRequestError({
        code: 'INVALID_CREDENTIALS',
        message: 'No account matches that email. Try signing up instead.',
        field: 'email',
      });
    }
    session.setToken(`${MOCK_TOKEN_PREFIX}${user.id}`);
    return user;
  },

  async signup({ name, email, collegeId, password }: SignupRequest): Promise<AuthUser> {
    await delay(450);
    const normalizedEmail = email.trim().toLowerCase();

    if (!name.trim()) {
      throw new ApiRequestError({ code: 'REQUIRED', message: 'Name is required.', field: 'name' });
    }
    if (!collegeId.trim()) {
      throw new ApiRequestError({ code: 'REQUIRED', message: 'College ID is required.', field: 'collegeId' });
    }
    if (password.length < 8) {
      throw new ApiRequestError({
        code: 'PASSWORD_TOO_SHORT',
        message: 'Password must be at least 8 characters.',
        field: 'password',
      });
    }
    if (findUserByEmail(normalizedEmail)) {
      throw new ApiRequestError({
        code: 'EMAIL_TAKEN',
        message: 'An account with this email already exists.',
        field: 'email',
      });
    }

    // New accounts always start as a plain member — roles are never
    // self-assigned on the client, only ever returned by the server.
    const user: AuthUser = {
      id: `user-signup-${Date.now()}-${++signupCounter}`,
      name: name.trim(),
      email: normalizedEmail,
      roles: ['member'],
    };
    saveSignedUpUser(user);
    session.setToken(`${MOCK_TOKEN_PREFIX}${user.id}`);
    return user;
  },

  async me(): Promise<AuthUser> {
    await delay(250);
    const token = session.getToken();
    const user = token?.startsWith(MOCK_TOKEN_PREFIX) ? findUserById(token.slice(MOCK_TOKEN_PREFIX.length)) : undefined;
    if (!user) {
      throw new ApiRequestError({ code: 'UNAUTHORIZED', message: 'No active session.' });
    }
    return user;
  },

  async logout(): Promise<void> {
    await delay(150);
    session.clearToken();
  },

  /** Exposed for the login screen so it can list demo accounts. */
  demoAccounts: Object.values(MOCK_USERS),
};
