import type { SelectHTMLAttributes } from 'react';
import { FormField } from './FormField';
import styles from './FormField.module.scss';

interface SelectOption {
  value: string;
  label: string;
}

interface SelectInputProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'id'> {
  label: string;
  required?: boolean;
  error?: string;
  hint?: string;
  options: SelectOption[];
}

export function SelectInput({ label, required, error, hint, options, className, ...rest }: SelectInputProps) {
  return (
    <FormField label={label} required={required} error={error} hint={hint}>
      {(ids) => (
        <select
          {...rest}
          {...ids}
          required={required}
          className={[styles.control, error ? styles.invalid : '', className].filter(Boolean).join(' ')}
        >
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      )}
    </FormField>
  );
}
