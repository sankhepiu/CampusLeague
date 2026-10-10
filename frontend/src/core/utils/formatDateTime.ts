/** Every timestamp the API sends is an ISO 8601 instant with an offset
 * (UTC "Z" or "+05:30"). `new Date(iso)` reads the instant correctly either
 * way, and `toLocale...String` without a `timeZone` option renders it in the
 * viewer's own time zone, so all times on screen are local. Always format
 * through these helpers so every page shows the same style.
 *
 * Calendar dates without a time ("2026-10-10", e.g. membership end dates)
 * are NOT instants: use membership/dates.ts `formatDate` for those. */
export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
}

export function formatDateOnly(iso: string): string {
  return new Date(iso).toLocaleDateString('en-IN', { dateStyle: 'medium' });
}

export function isPast(iso: string): boolean {
  return new Date(iso).getTime() < Date.now();
}
