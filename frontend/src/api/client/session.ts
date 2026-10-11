const TOKEN_KEY = 'campusleague.auth.token';
const CLUB_KEY = 'campusleague.auth.club';

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
  /** Slug of the club this token belongs to; sent as `X-Club` on every request. */
  getClub(): string | null {
    try {
      return localStorage.getItem(CLUB_KEY);
    } catch {
      return null;
    }
  },
  setClub(slug: string): void {
    try {
      localStorage.setItem(CLUB_KEY, slug);
    } catch {
      /* ignore */
    }
  },
  clearToken(): void {
    try {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(CLUB_KEY);
    } catch {
      /* ignore */
    }
  },
};
