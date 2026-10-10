import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import styles from './PageShell.module.scss';

interface PageShellProps {
  title: string;
  children: ReactNode;
  /** 'dotted' recolors in the palette for member-facing areas (Membership,
   * Member Card, Settings) so they read as their own zone. */
  background?: 'default' | 'dotted';
}

/** Consistent page header + back-to-home link wrapping each feature area. */
export function PageShell({ title, children, background = 'default' }: PageShellProps) {
  const classes = [styles.shell, background === 'dotted' ? styles.dotted : ''].filter(Boolean).join(' ');
  return (
    <div className={classes}>
      <div className={styles.header}>
        <h1 className={styles.title}>{title}</h1>
        <Link to="/home" className={styles.back}>
          ← Back to Home
        </Link>
      </div>
      {children}
    </div>
  );
}
