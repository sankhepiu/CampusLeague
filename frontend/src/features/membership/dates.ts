export function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function addMonths(dateStr: string, months: number): string {
  const d = new Date(`${dateStr}T00:00:00`);
  d.setMonth(d.getMonth() + months);
  return d.toISOString().slice(0, 10);
}

export function addDays(dateStr: string, days: number): string {
  const d = new Date(`${dateStr}T00:00:00`);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

export function formatDate(dateStr: string): string {
  return new Date(`${dateStr}T00:00:00`).toLocaleDateString('en-IN', { year: 'numeric', month: 'short', day: 'numeric' });
}

export function daysUntil(dateStr: string): number {
  const ms = new Date(`${dateStr}T00:00:00`).getTime() - new Date(`${today()}T00:00:00`).getTime();
  return Math.round(ms / (1000 * 60 * 60 * 24));
}
