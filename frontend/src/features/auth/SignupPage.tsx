import { AuthPage } from './AuthPage';

/** Route-level wrapper so /signup opens the shared auth page on the Sign Up tab. */
export function SignupPage() {
  return <AuthPage initialTab="signup" />;
}
