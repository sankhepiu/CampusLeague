import styles from './Toggle.module.scss';

interface ToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
}

/** A labeled on/off switch, keyboard operable (Space/Enter via native button). */
export function Toggle({ checked, onChange, label }: ToggleProps) {
  return (
    <div className={styles.row}>
      <span>{label}</span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        className={styles.track}
        onClick={() => onChange(!checked)}
      >
        <span className={styles.thumb} aria-hidden="true" />
      </button>
    </div>
  );
}
