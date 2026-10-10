import { AuthPage } from './AuthPage';

/** Route-level wrapper so /login opens the shared auth page on the Log In tab. */
export function LoginPage() {
  return <AuthPage initialTab="login" />;
}
