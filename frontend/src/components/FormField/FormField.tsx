import { useId, type ReactNode } from 'react';
import styles from './FormField.module.scss';

interface FormFieldProps {
  label: string;
  required?: boolean;
  error?: string;
  hint?: string;
  /** Receives the ids to spread onto the actual control for correct a11y wiring. */
  children: (ids: { id: string; 'aria-describedby'?: string; 'aria-invalid'?: boolean }) => ReactNode;
}

/** Lays out a label + control + inline error/hint with the control's
 * accessible name and description wired up automatically. */
export function FormField({ label, required, error, hint, children }: FormFieldProps) {
  const id = useId();
  const errorId = error ? `${id}-error` : undefined;
  const hintId = hint ? `${id}-hint` : undefined;
  const describedBy = [errorId, hintId].filter(Boolean).join(' ') || undefined;

  return (
    <div className={styles.field}>
      <label className={styles.label} htmlFor={id}>
        {label}
        {/* Asterisk is CSS-generated content, not DOM text, so it can never
            leak into the label's computed accessible name (some browsers
            don't fully exclude aria-hidden text nodes from "name from
            content"). aria-hidden stays as a second line of defense. */}
        {required && <span className={styles.required} aria-hidden="true" />}
      </label>
      {children({ id, 'aria-describedby': describedBy, 'aria-invalid': !!error })}
      {hint && !error && (
        <p className={styles.hint} id={hintId}>
          {hint}
        </p>
      )}
      {error && (
        <p className={styles.error} id={errorId} role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
