import type { ReactNode } from 'react';
import styles from './StatusBadge.module.scss';

export type StatusBadgeVariant = 'neutral' | 'success' | 'danger' | 'warning' | 'info';

interface StatusBadgeProps {
  variant?: StatusBadgeVariant;
  children: ReactNode;
}

export function StatusBadge({ variant = 'neutral', children }: StatusBadgeProps) {
  return <span className={`${styles.badge} ${styles[variant]}`}>{children}</span>;
}
