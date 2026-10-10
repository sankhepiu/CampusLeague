import { ApiRequestError, session } from '../../api/client';
import type { AuthUser, LoginRequest, SignupRequest, SignupResult, VerifyEmailRequest } from './types';
import { createUser, DEMO_ACCOUNT_EMAILS, findUserByEmail, getCurrentMockUser, MOCK_TOKEN_PREFIX } from './mockUsers';

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Mock mode has no inbox, so every verification code is this fixed value
 * (the verify screen says so). Rules otherwise mirror the backend: valid for
 * 10 minutes, void after 5 wrong attempts, replaced by a resend. */
export const MOCK_VERIFICATION_CODE = '123456';
const CODE_TTL_MS = 10 * 60_000;
const MAX_ATTEMPTS = 5;
const PENDING_KEY = 'campusleague.mock.pendingSignups';

interface PendingSignup {
  user: Omit<AuthUser, 'id'>;
  attempts: number;
  expiresAt: number;
}

function loadPending(): Record<string, PendingSignup> {
  try {
    const raw = localStorage.getItem(PENDING_KEY);
    if (raw) return JSON.parse(raw) as Record<string, PendingSignup>;
  } catch {
    /* storage unavailable or corrupt */
  }
  return {};
}

function savePending(pending: Record<string, PendingSignup>): void {
  try {
    localStorage.setItem(PENDING_KEY, JSON.stringify(pending));
  } catch {
    /* storage unavailable */
  }
}

export const mockAuthApi = {
  async login({ email, password }: LoginRequest): Promise<AuthUser> {
    await delay(400);
    if (!email.trim() || !password) {
      throw new ApiRequestError({
        code: 'validation_error',
        message: 'Email and password are required.',
        field: !email.trim() ? 'email' : 'password',
      });
    }
    // Mock mode accepts any password for a known email, matching the real
    // endpoint's "wrong email, wrong password... response is identical" rule
    // only in that we never reveal *which* part was wrong.
    const user = findUserByEmail(email);
    if (!user) {
      // Signed up but not yet verified: same 403 the real backend gives once
      // the password matches (mock mode accepts any password).
      if (loadPending()[email.trim().toLowerCase()]) {
        throw new ApiRequestError({
          code: 'email_not_verified',
          message: 'Verify your email address before logging in. Enter the code we emailed you.',
        });
      }
      throw new ApiRequestError({ code: 'invalid_credentials', message: 'Incorrect email or password.' });
    }
    session.setToken(`${MOCK_TOKEN_PREFIX}${user.id}`);
    return user;
  },

  async signup({ name, email, collegeId, password, phone }: SignupRequest): Promise<SignupResult> {
    await delay(450);
    const normalizedEmail = email.trim().toLowerCase();
    const errors: { field: string; code: string; message: string }[] = [];

    if (!name.trim()) errors.push({ field: 'name', code: 'blank', message: 'This field may not be blank.' });
    if (!collegeId.trim()) errors.push({ field: 'college_id', code: 'blank', message: 'This field may not be blank.' });
    if (!EMAIL_PATTERN.test(normalizedEmail)) {
      errors.push({ field: 'email', code: 'invalid', message: 'Enter a valid email address.' });
    } else if (findUserByEmail(normalizedEmail) || loadPending()[normalizedEmail]) {
      errors.push({ field: 'email', code: 'email_taken', message: 'An account with this email already exists.' });
    }
    if (password.length < 8) {
      errors.push({ field: 'password', code: 'password_too_short', message: 'Password must be at least 8 characters.' });
    }

    if (errors.length > 0) {
      throw new ApiRequestError({
        code: 'validation_error',
        message: errors[0].message,
        field: errors[0].field,
        errors,
      });
    }

    // New accounts always start as a plain member with no committee role and
    // no membership — roles and membershipStatus are never client-chosen,
    // they only ever come back from the server. The account is held as
    // "pending" (no token, cannot log in) until its email is verified.
    const pending = loadPending();
    pending[normalizedEmail] = {
      user: {
        name: name.trim(),
        email: normalizedEmail,
        collegeId: collegeId.trim(),
        phone: phone?.trim() ?? '',
        roles: [],
        membershipStatus: 'none',
      },
      attempts: 0,
      expiresAt: Date.now() + CODE_TTL_MS,
    };
    savePending(pending);
    return { verificationRequired: true, email: normalizedEmail };
  },

  async verifyEmail({ email, code }: VerifyEmailRequest): Promise<AuthUser> {
    await delay(400);
    const normalizedEmail = email.trim().toLowerCase();
    const pending = loadPending();
    const record = pending[normalizedEmail];
    // Unknown email and already-verified account look like a wrong code,
    // exactly as on the real backend.
    if (!record) throw new ApiRequestError({ code: 'invalid_code', message: 'That code is not correct.' });
    if (record.attempts >= MAX_ATTEMPTS) {
      throw new ApiRequestError({ code: 'too_many_attempts', message: 'Too many wrong attempts. Request a new code.' });
    }
    if (Date.now() >= record.expiresAt) {
      throw new ApiRequestError({ code: 'code_expired', message: 'That code has expired. Request a new one.' });
    }
    if (code.trim() !== MOCK_VERIFICATION_CODE) {
      record.attempts += 1;
      savePending(pending);
      if (record.attempts >= MAX_ATTEMPTS) {
        throw new ApiRequestError({ code: 'too_many_attempts', message: 'Too many wrong attempts. Request a new code.' });
      }
      throw new ApiRequestError({ code: 'invalid_code', message: 'That code is not correct.' });
    }

    const user = createUser(record.user);
    delete pending[normalizedEmail];
    savePending(pending);
    session.setToken(`${MOCK_TOKEN_PREFIX}${user.id}`);
    return user;
  },

  /** Like the real endpoint, this never says whether the address exists. */
  async resendCode(email: string): Promise<void> {
    await delay(300);
    const pending = loadPending();
    const record = pending[email.trim().toLowerCase()];
    if (record) {
      record.attempts = 0;
      record.expiresAt = Date.now() + CODE_TTL_MS;
      savePending(pending);
    }
  },

  async me(): Promise<AuthUser> {
    await delay(250);
    const user = getCurrentMockUser();
    if (!user) {
      throw new ApiRequestError({ code: 'not_authenticated', message: 'No active session.' });
    }
    return user;
  },

  async logout(): Promise<void> {
    await delay(150);
    session.clearToken();
  },

  /** Exposed for the login screen so it can list demo accounts. */
  demoAccounts: DEMO_ACCOUNT_EMAILS.map((email) => findUserByEmail(email)).filter((u): u is AuthUser => !!u),
};
