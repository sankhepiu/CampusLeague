import type { CSSProperties } from 'react';
import styles from './Spinner.module.scss';

interface SpinnerProps {
  label?: string;
  size?: number;
  fullPage?: boolean;
}

/** Loading indicator for both inline and full-page use. */
export function Spinner({ label = 'Loading…', size, fullPage }: SpinnerProps) {
  const glyph = (
    <span
      className={styles.glyph}
      style={size ? ({ '--cl-spinner-size': `${size}px` } as CSSProperties) : undefined}
      aria-hidden="true"
    />
  );

  if (fullPage) {
    return (
      <div className={styles.fullPage} role="status" aria-live="polite">
        {glyph}
        <span className={styles.label}>{label}</span>
      </div>
    );
  }

  return (
    <span className={styles.spinner} role="status" aria-live="polite">
      {glyph}
      <span className="sr-only" style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden' }}>
        {label}
      </span>
    </span>
  );
}
