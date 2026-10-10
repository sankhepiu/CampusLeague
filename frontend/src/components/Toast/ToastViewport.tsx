import type { ToastItem } from './Toast.types';
import styles from './Toast.module.scss';

interface ToastViewportProps {
  toasts: ToastItem[];
  onDismiss: (id: string) => void;
}

const ICON: Record<ToastItem['variant'], string> = { success: '✓', error: '!', info: 'i' };

export function ToastViewport({ toasts, onDismiss }: ToastViewportProps) {
  if (toasts.length === 0) return null;

  return (
    <div className={styles.viewport} aria-live="polite">
      {toasts.map((toast) => (
        <div key={toast.id} className={`${styles.toast} ${styles[toast.variant]}`} role="status">
          <span aria-hidden="true">{ICON[toast.variant]}</span>
          <span>{toast.message}</span>
          <button type="button" className={styles.close} onClick={() => onDismiss(toast.id)} aria-label="Dismiss notification">
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}
