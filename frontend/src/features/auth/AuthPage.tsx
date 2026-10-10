import { useState, type FormEvent } from 'react';
import { Navigate } from 'react-router-dom';
import { Panel } from '../../components/Panel/Panel';
import { TextInput } from '../../components/FormField/TextInput';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { PixelIcon } from '../../components/PixelIcon';
import type { ApiError } from '../../api/client';
import { env } from '../../core/config/env';
import { useAuth } from '../../core/hooks/useAuth';
import { mockAuthApi } from './api.mock';
import { demoAccountLabel } from './mockUsers';
import { isValidEmail, MIN_PASSWORD_LENGTH } from './validation';
import styles from './AuthPage.module.scss';

// The server reports fields by their wire (snake_case) name; our form state
// uses camelCase, so translate before matching a server error to a field.
const SERVER_FIELD_TO_FORM_FIELD: Record<string, string> = { college_id: 'collegeId' };
const toFormField = (field: string) => SERVER_FIELD_TO_FORM_FIELD[field] ?? field;

type Tab = 'login' | 'signup';
type Phase = 'idle' | 'submitting' | 'success';

interface LoginForm {
  email: string;
  password: string;
}

interface SignupForm {
  name: string;
  email: string;
  collegeId: string;
  password: string;
  confirmPassword: string;
}

const EMPTY_LOGIN: LoginForm = { email: '', password: '' };
const EMPTY_SIGNUP: SignupForm = { name: '', email: '', collegeId: '', password: '', confirmPassword: '' };

interface AuthPageProps {
  initialTab: Tab;
}

/** Single NES-container auth page with Log in / Sign up tabs. Roles are never
 * chosen here — they only ever come back from the server on login/signup/me. */
export function AuthPage({ initialTab }: AuthPageProps) {
  const { status, login, signup } = useAuth();

  const [tab, setTab] = useState<Tab>(initialTab);
  const [phase, setPhase] = useState<Phase>('idle');
  // Normally the redirect fires the instant `status` flips to authenticated.
  // After a fresh submit we hold it back briefly so the success state is
  // actually visible instead of being skipped in the same render.
  const [redirectReady, setRedirectReady] = useState(true);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const [loginForm, setLoginForm] = useState<LoginForm>(EMPTY_LOGIN);
  const [signupForm, setSignupForm] = useState<SignupForm>(EMPTY_SIGNUP);

  // Always /home, never back to wherever ProtectedRoute bounced them from —
  // the demo wants a single, predictable landing spot every time.
  if (status === 'authenticated' && redirectReady) {
    return <Navigate to="/home" replace />;
  }

  const switchTab = (next: Tab) => {
    setTab(next);
    setFieldErrors({});
    setGeneralError(null);
    setPhase('idle');
  };

  const validateLogin = (): Record<string, string> => {
    const errors: Record<string, string> = {};
    if (!loginForm.email.trim()) errors.email = 'Email is required.';
    else if (!isValidEmail(loginForm.email)) errors.email = 'Enter a valid email address.';
    if (!loginForm.password) errors.password = 'Password is required.';
    return errors;
  };

  const validateSignup = (): Record<string, string> => {
    const errors: Record<string, string> = {};
    if (!signupForm.name.trim()) errors.name = 'Name is required.';
    if (!signupForm.email.trim()) errors.email = 'Email is required.';
    else if (!isValidEmail(signupForm.email)) errors.email = 'Enter a valid email address.';
    if (!signupForm.collegeId.trim()) errors.collegeId = 'College ID is required.';
    if (!signupForm.password) errors.password = 'Password is required.';
    else if (signupForm.password.length < MIN_PASSWORD_LENGTH) {
      errors.password = `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
    }
    if (!signupForm.confirmPassword) errors.confirmPassword = 'Please confirm your password.';
    else if (signupForm.confirmPassword !== signupForm.password) errors.confirmPassword = 'Passwords do not match.';
    return errors;
  };

  const runSubmit = async (validate: () => Record<string, string>, action: () => Promise<void>) => {
    const errors = validate();
    setFieldErrors(errors);
    setGeneralError(null);
    if (Object.keys(errors).length > 0) return;

    setPhase('submitting');
    setRedirectReady(false);
    try {
      await action();
      setPhase('success');
      setTimeout(() => setRedirectReady(true), 500);
    } catch (err) {
      setPhase('idle');
      setRedirectReady(true);
      const apiError = err as ApiError;
      if (apiError?.errors && apiError.errors.length > 0) {
        const perField: Record<string, string> = {};
        for (const fieldError of apiError.errors) {
          perField[toFormField(fieldError.field)] = fieldError.message;
        }
        setFieldErrors(perField);
      } else if (apiError?.field) {
        setFieldErrors({ [toFormField(apiError.field)]: apiError.message });
      } else {
        setGeneralError(apiError?.message ?? 'Something went wrong. Please try again.');
      }
    }
  };

  const onLoginSubmit = (e: FormEvent) => {
    e.preventDefault();
    void runSubmit(validateLogin, () => login(loginForm.email, loginForm.password));
  };

  const onSignupSubmit = (e: FormEvent) => {
    e.preventDefault();
    void runSubmit(validateSignup, () =>
      signup({
        name: signupForm.name.trim(),
        email: signupForm.email.trim(),
        collegeId: signupForm.collegeId.trim(),
        password: signupForm.password,
      }),
    );
  };

  const submitting = phase === 'submitting';
  const buttonLabel = (idleLabel: string) => {
    if (phase === 'submitting') return <Spinner size={16} label={idleLabel} />;
    if (phase === 'success') return 'Success!';
    return idleLabel;
  };

  return (
    <div className={styles.wrapper}>
      <Panel className={styles.card} accent="var(--cl-violet)">
        <div className={styles.brand}>
          <PixelIcon name="coin" size={40} />
          <h1 className={styles.title}>Campus League</h1>
        </div>

        <div className={styles.tabs} role="tablist" aria-label="Authentication mode">
          <button
            type="button"
            role="tab"
            id="auth-tab-login"
            aria-selected={tab === 'login'}
            aria-controls="auth-panel-login"
            className={`${styles.tab} ${tab === 'login' ? styles.tabActive : ''}`}
            onClick={() => switchTab('login')}
          >
            Log In
          </button>
          <button
            type="button"
            role="tab"
            id="auth-tab-signup"
            aria-selected={tab === 'signup'}
            aria-controls="auth-panel-signup"
            className={`${styles.tab} ${tab === 'signup' ? styles.tabActive : ''}`}
            onClick={() => switchTab('signup')}
          >
            Sign Up
          </button>
        </div>

        {generalError && <ErrorBox error={generalError} />}

        {tab === 'login' ? (
          <form id="auth-panel-login" role="tabpanel" aria-labelledby="auth-tab-login" onSubmit={onLoginSubmit} noValidate>
            <TextInput
              label="Email"
              type="email"
              required
              value={loginForm.email}
              onChange={(e) => setLoginForm((f) => ({ ...f, email: e.target.value }))}
              error={fieldErrors.email}
              autoComplete="username"
            />
            <TextInput
              label="Password"
              type="password"
              required
              value={loginForm.password}
              onChange={(e) => setLoginForm((f) => ({ ...f, password: e.target.value }))}
              error={fieldErrors.password}
              autoComplete="current-password"
            />
            <button type="submit" className={styles.submit} disabled={submitting}>
              {buttonLabel('Sign In')}
            </button>
          </form>
        ) : (
          <form id="auth-panel-signup" role="tabpanel" aria-labelledby="auth-tab-signup" onSubmit={onSignupSubmit} noValidate>
            <TextInput
              label="Name"
              required
              value={signupForm.name}
              onChange={(e) => setSignupForm((f) => ({ ...f, name: e.target.value }))}
              error={fieldErrors.name}
              autoComplete="name"
            />
            <TextInput
              label="Email"
              type="email"
              required
              value={signupForm.email}
              onChange={(e) => setSignupForm((f) => ({ ...f, email: e.target.value }))}
              error={fieldErrors.email}
              autoComplete="username"
            />
            <TextInput
              label="College ID"
              required
              value={signupForm.collegeId}
              onChange={(e) => setSignupForm((f) => ({ ...f, collegeId: e.target.value }))}
              error={fieldErrors.collegeId}
            />
            <TextInput
              label="Password"
              type="password"
              required
              hint={fieldErrors.password ? undefined : `At least ${MIN_PASSWORD_LENGTH} characters.`}
              value={signupForm.password}
              onChange={(e) => setSignupForm((f) => ({ ...f, password: e.target.value }))}
              error={fieldErrors.password}
              autoComplete="new-password"
            />
            <TextInput
              label="Confirm Password"
              type="password"
              required
              value={signupForm.confirmPassword}
              onChange={(e) => setSignupForm((f) => ({ ...f, confirmPassword: e.target.value }))}
              error={fieldErrors.confirmPassword}
              autoComplete="new-password"
            />
            <button type="submit" className={styles.submit} disabled={submitting}>
              {buttonLabel('Create Account')}
            </button>
          </form>
        )}

        {env.useMockApi && tab === 'login' && (
          <div className={styles.demo}>
            <p className={styles.demoTitle}>Demo accounts (mock mode, any password):</p>
            <div className={styles.demoList}>
              {mockAuthApi.demoAccounts.map((account) => (
                <button
                  key={account.email}
                  type="button"
                  className={styles.demoButton}
                  onClick={() => {
                    setLoginForm({ email: account.email, password: 'demo' });
                  }}
                >
                  <span className={styles.demoRole}>{demoAccountLabel(account)}</span>
                  <span className={styles.demoEmail}>{account.email}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </Panel>
    </div>
  );
}
