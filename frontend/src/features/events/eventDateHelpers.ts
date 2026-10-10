/** Converts between an ISO timestamp (with offset, as the contract sends)
 * and the value an <input type="datetime-local"> needs/produces (no offset,
 * interpreted in the browser's local time either way). */
export function toDatetimeLocalValue(iso: string): string {
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function fromDatetimeLocalValue(value: string): string {
  return new Date(value).toISOString();
}

export function rupeesToPaise(rupees: string): number {
  const n = Number(rupees);
  return Number.isFinite(n) ? Math.round(n * 100) : 0;
}

export function paiseToRupeesInput(paise: number): string {
  return (paise / 100).toString();
}
