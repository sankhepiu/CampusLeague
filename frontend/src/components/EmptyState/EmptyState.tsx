import type { ReactNode } from 'react';
import { PixelIcon, type PixelIconName } from '../PixelIcon';
import styles from './EmptyState.module.scss';

interface EmptyStateProps {
  icon?: PixelIconName;
  title: string;
  message?: string;
  action?: ReactNode;
}

export function EmptyState({ icon = 'ghost', title, message, action }: EmptyStateProps) {
  return (
    <div className={styles.wrapper}>
      <PixelIcon name={icon} size={56} />
      <h3 className={styles.title}>{title}</h3>
      {message && <p className={styles.message}>{message}</p>}
      {action && <div className={styles.action}>{action}</div>}
    </div>
  );
}
