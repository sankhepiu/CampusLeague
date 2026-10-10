import type { ApiError } from '../../api/client';
import styles from './ErrorBox.module.scss';

interface ErrorBoxProps {
  error: ApiError | string;
  onRetry?: () => void;
}

/** User-friendly error presentation — never renders stack traces or raw
 * server detail, only the normalized `{ code, message, field }` shape. */
export function ErrorBox({ error, onRetry }: ErrorBoxProps) {
  const message = typeof error === 'string' ? error : error.message;

  return (
    <div className={styles.box} role="alert">
      <span className={styles.icon} aria-hidden="true">
        !
      </span>
      <div>
        <p className={styles.title}>Something went wrong</p>
        <p className={styles.message}>{message}</p>
        {onRetry && (
          <button type="button" className={styles.retry} onClick={onRetry}>
            Try Again
          </button>
        )}
      </div>
    </div>
  );
}
