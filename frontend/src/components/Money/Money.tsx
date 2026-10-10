import { formatPaiseToINR } from './formatCurrency';

interface MoneyProps {
  paise: number;
  className?: string;
}

/** Displays an integer-paise amount as formatted INR, coloring negative values
 * and using tabular numerals so figures align in columns (tables, totals). */
export function Money({ paise, className }: MoneyProps) {
  const negative = paise < 0;
  const classes = ['cl-tabular-nums', className].filter(Boolean).join(' ');
  return (
    <span className={classes} style={{ color: negative ? 'var(--cl-color-danger)' : undefined }}>
      {formatPaiseToINR(paise)}
    </span>
  );
}
