const TOKEN_KEY = 'campusleague.auth.token';

/** Minimal token store backed by localStorage. Real backends may instead rely on
 * an httpOnly session cookie, in which case `getToken`/`setToken` become no-ops
 * and the browser handles the session automatically. */
export const session = {
  getToken(): string | null {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  setToken(token: string): void {
    try {
      localStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* storage unavailable (private mode, etc.) */
    }
  },
  clearToken(): void {
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* ignore */
    }
  },
};
