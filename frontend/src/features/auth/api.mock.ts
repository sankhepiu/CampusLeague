import { ApiRequestError, session } from '../../api/client';
import type { AuthUser, LoginRequest, SignupRequest } from './types';
import { createUser, DEMO_ACCOUNT_EMAILS, findUserByEmail, getCurrentMockUser, MOCK_TOKEN_PREFIX } from './mockUsers';

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

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
      throw new ApiRequestError({ code: 'invalid_credentials', message: 'Incorrect email or password.' });
    }
    session.setToken(`${MOCK_TOKEN_PREFIX}${user.id}`);
    return user;
  },

  async signup({ name, email, collegeId, password, phone }: SignupRequest): Promise<AuthUser> {
    await delay(450);
    const normalizedEmail = email.trim().toLowerCase();
    const errors: { field: string; code: string; message: string }[] = [];

    if (!name.trim()) errors.push({ field: 'name', code: 'blank', message: 'This field may not be blank.' });
    if (!collegeId.trim()) errors.push({ field: 'college_id', code: 'blank', message: 'This field may not be blank.' });
    if (!EMAIL_PATTERN.test(normalizedEmail)) {
      errors.push({ field: 'email', code: 'invalid', message: 'Enter a valid email address.' });
    } else if (findUserByEmail(normalizedEmail)) {
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
    // they only ever come back from the server.
    const user = createUser({
      name: name.trim(),
      email: normalizedEmail,
      collegeId: collegeId.trim(),
      phone: phone?.trim() ?? '',
      roles: [],
      membershipStatus: 'none',
    });
    session.setToken(`${MOCK_TOKEN_PREFIX}${user.id}`);
    return user;
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
