import { useEffect, useState, type FormEvent } from 'react';
import { TextInput } from '../../components/FormField/TextInput';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import type { ApiError } from '../../api/client';
import { env } from '../../core/config/env';
import { useAuth } from '../../core/hooks/useAuth';
import { MOCK_VERIFICATION_CODE } from './api.mock';
import styles from './AuthPage.module.scss';

/** The backend sends at most one code per 60 seconds and gives no error
 * when asked sooner (it answers `{sent: true}` either way), so the button
 * enforces the wait itself. */
export const RESEND_COOLDOWN_SECONDS = 60;
const CODE_LENGTH = 6;

/** Plain-language text for each verify-email failure in the contract. */
function messageFor(error: ApiError): string {
  switch (error.code) {
    case 'invalid_code':
      return 'Wrong code. Check the email and try again.';
    case 'code_expired':
      return 'That code has expired. Resend a new code below.';
    case 'too_many_attempts':
      return 'Too many wrong attempts. Resend a new code below.';
    case 'throttled':
      return 'Too many requests. Wait a minute and try again.';
    default:
      return error.message || 'Something went wrong. Please try again.';
  }
}

interface VerifyEmailPanelProps {
  email: string;
  /** Name of the club the account is being created in. */
  clubName?: string;
  /** Seconds the Resend button starts disabled for: 60 straight after
   * signup (a code was just sent), 0 when arriving from a blocked login. */
  initialCooldown: number;
  /** Shown above the form, e.g. why the visitor landed here. */
  notice?: string;
  /** Called whenever a code is (re)sent, so the parent can remember when. */
  onCodeSent: () => void;
  onBack: () => void;
}

/** Step two of signup: enter the 6-digit code that was emailed. A correct
 * code signs the user in (AuthPage then redirects to /home). */
export function VerifyEmailPanel({ email, clubName, initialCooldown, notice, onCodeSent, onBack }: VerifyEmailPanelProps) {
  const { verifyEmail, resendCode } = useAuth();

  const [code, setCode] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [resending, setResending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(notice ?? null);
  // After too many wrong attempts (or expiry) the current code is dead:
  // further guesses are pointless until a new one is requested.
  const [needsNewCode, setNeedsNewCode] = useState(false);
  const [cooldown, setCooldown] = useState(initialCooldown);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setTimeout(() => setCooldown((seconds) => seconds - 1), 1000);
    return () => clearTimeout(timer);
  }, [cooldown]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (code.length !== CODE_LENGTH || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await verifyEmail(email, code);
      // Signed in: AuthPage sees the authenticated status and redirects.
    } catch (err) {
      const apiError = err as ApiError;
      setError(messageFor(apiError));
      if (apiError.code === 'too_many_attempts' || apiError.code === 'code_expired') setNeedsNewCode(true);
      setCode('');
      setSubmitting(false);
    }
  };

  const onResend = async () => {
    if (cooldown > 0 || resending) return;
    setResending(true);
    setError(null);
    try {
      await resendCode(email);
      setInfo(`If ${email} has an account waiting to be verified, a new code is on its way. Earlier codes no longer work.`);
      setNeedsNewCode(false);
      setCode('');
      setCooldown(RESEND_COOLDOWN_SECONDS);
      onCodeSent();
    } catch (err) {
      setError(messageFor(err as ApiError));
    } finally {
      setResending(false);
    }
  };

  return (
    <div>
      <h2 className={styles.verifyTitle}>Verify your email</h2>
      {clubName && <p className={styles.verifyText}>Joining {clubName}</p>}
      <p className={styles.verifyText}>
        We emailed a {CODE_LENGTH}-digit code to <strong>{email}</strong>. Enter it to finish signing up. The code works for 10 minutes.
      </p>

      {env.useMockApi ? (
        <p className={styles.verifyHint}>Mock mode: no email is sent. The code is {MOCK_VERIFICATION_CODE}.</p>
      ) : (
        import.meta.env.DEV && <p className={styles.verifyHint}>Development: the email is printed in the backend's runserver terminal.</p>
      )}

      {info && !error && (
        <p className={styles.verifyInfo} role="status">
          {info}
        </p>
      )}
      {error && <ErrorBox error={error} />}

      <form onSubmit={onSubmit} noValidate>
        <TextInput
          label="Verification code"
          required
          value={code}
          // Digits only, at most six: pasting "482 913" or "482-913" still works.
          onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, CODE_LENGTH))}
          inputMode="numeric"
          autoComplete="one-time-code"
          placeholder="6 digits"
          maxLength={CODE_LENGTH + 2}
          disabled={submitting || needsNewCode}
          autoFocus
          className={styles.codeInput}
        />
        <button type="submit" className={styles.submit} disabled={submitting || needsNewCode || code.length !== CODE_LENGTH}>
          {submitting ? <Spinner size={16} label="Verifying" /> : 'Verify Email'}
        </button>
      </form>

      <div className={styles.verifyActions}>
        <button type="button" className={styles.linkButton} onClick={() => void onResend()} disabled={cooldown > 0 || resending}>
          {resending ? 'Sending…' : cooldown > 0 ? `Resend code in ${cooldown}s` : 'Resend code'}
        </button>
        <button type="button" className={styles.linkButton} onClick={onBack} disabled={submitting}>
          Back to log in
        </button>
      </div>
    </div>
  );
}
