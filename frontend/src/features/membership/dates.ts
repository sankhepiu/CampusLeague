/** Helpers for calendar dates ("YYYY-MM-DD", no time), such as membership
 * start and end dates. Everything here works in the viewer's local time
 * zone. Never go through `toISOString()` for these: it converts to UTC, and
 * east of Greenwich local midnight is still the previous day in UTC, which
 * silently shifts the date back by one. */

const pad = (n: number) => String(n).padStart(2, '0');

/** A local Date as "YYYY-MM-DD", read from its local year, month and day. */
function toDateString(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** "YYYY-MM-DD" as a Date at local midnight. */
function fromDateString(dateStr: string): Date {
  return new Date(`${dateStr}T00:00:00`);
}

export function today(): string {
  return toDateString(new Date());
}

export function addMonths(dateStr: string, months: number): string {
  const d = fromDateString(dateStr);
  d.setMonth(d.getMonth() + months);
  return toDateString(d);
}

export function addDays(dateStr: string, days: number): string {
  const d = fromDateString(dateStr);
  d.setDate(d.getDate() + days);
  return toDateString(d);
}

export function formatDate(dateStr: string): string {
  return fromDateString(dateStr).toLocaleDateString('en-IN', { year: 'numeric', month: 'short', day: 'numeric' });
}

export function daysUntil(dateStr: string): number {
  const ms = fromDateString(dateStr).getTime() - fromDateString(today()).getTime();
  return Math.round(ms / (1000 * 60 * 60 * 24));
}
