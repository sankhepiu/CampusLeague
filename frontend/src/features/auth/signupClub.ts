/** The club a visitor chose on the Sign Up tab. It must survive the step
 * from "signup" to "enter the emailed code" (and a page refresh in between),
 * because verify-email and resend-code must name the same club as signup. */
const KEY = 'campusleague.auth.signupClub';

export const signupClub = {
  get(): string | null {
    try {
      return sessionStorage.getItem(KEY);
    } catch {
      return null;
    }
  },
  set(slug: string): void {
    try {
      sessionStorage.setItem(KEY, slug);
    } catch {
      /* storage unavailable: falls back to the default club */
    }
  },
  clear(): void {
    try {
      sessionStorage.removeItem(KEY);
    } catch {
      /* ignore */
    }
  },
};

/** `X-Club` for a signup-flow request; nothing when no club was chosen. */
export function clubHeader(slug: string | null): Record<string, string> | undefined {
  return slug ? { 'X-Club': slug } : undefined;
}
