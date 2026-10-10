import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import styles from './PageShell.module.scss';

interface PageShellProps {
  title: string;
  children: ReactNode;
}

/** Consistent page header + back-to-home link wrapping each feature area. */
export function PageShell({ title, children }: PageShellProps) {
  return (
    <div className={styles.shell}>
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
