import type { ReactNode } from 'react';
import { StatusBadge } from '../StatusBadge/StatusBadge';
import styles from './ProgressBar.module.scss';

interface ProgressBarProps {
  /** 0–100, already capped by the caller/server. */
  percent: number;
  label?: ReactNode;
  /** When provided, renders an "On track" / "Behind" badge next to the label. */
  onTrack?: boolean;
}

export function ProgressBar({ percent, label, onTrack }: ProgressBarProps) {
  const clamped = Math.max(0, Math.min(100, percent));
  return (
    <div>
      {(label || onTrack !== undefined) && (
        <div className={styles.row}>
          {label && <span className={styles.amount}>{label}</span>}
          {onTrack !== undefined && <StatusBadge variant={onTrack ? 'success' : 'warning'}>{onTrack ? 'On track' : 'Behind'}</StatusBadge>}
        </div>
      )}
      <div className={styles.track} role="progressbar" aria-valuenow={clamped} aria-valuemin={0} aria-valuemax={100}>
        <div className={`${styles.fill} ${onTrack === false ? styles.fillBehind : ''}`} style={{ width: `${clamped}%` }} />
      </div>
    </div>
  );
}
