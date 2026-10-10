const INR_FORMATTER = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Converts integer paise (1/100 of a rupee) into an Indian-formatted rupee
 * string, e.g. 150075 -> "₹1,500.75". Negative and zero values are handled;
 * all math stays in integer paise until the final division to avoid
 * floating-point rounding drift. */
export function formatPaiseToINR(paise: number): string {
  if (!Number.isFinite(paise)) return INR_FORMATTER.format(0);
  const rupees = Math.trunc(paise) / 100;
  return INR_FORMATTER.format(rupees);
}
