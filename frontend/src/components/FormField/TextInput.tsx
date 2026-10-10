import type { InputHTMLAttributes } from 'react';
import { FormField } from './FormField';
import styles from './FormField.module.scss';

interface TextInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id'> {
  label: string;
  required?: boolean;
  error?: string;
  hint?: string;
}

export function TextInput({ label, required, error, hint, className, ...rest }: TextInputProps) {
  return (
    <FormField label={label} required={required} error={error} hint={hint}>
      {(ids) => (
        <input
          {...rest}
          {...ids}
          required={required}
          className={[styles.control, error ? styles.invalid : '', className].filter(Boolean).join(' ')}
        />
      )}
    </FormField>
  );
}
