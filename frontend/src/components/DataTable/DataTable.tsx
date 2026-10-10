import type { ReactNode } from 'react';
import type { ApiError } from '../../api/client';
import { EmptyState } from '../EmptyState/EmptyState';
import { ErrorBox } from '../ErrorBox/ErrorBox';
import { Spinner } from '../Spinner/Spinner';
import styles from './DataTable.module.scss';

export interface DataTableColumn<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  /** Right-aligns the header and every cell in this column — for dense
   * money/figure tables (finance), where right-aligned columns read faster
   * than left-aligned ones. Defaults to left. */
  align?: 'left' | 'right';
}

interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  isLoading?: boolean;
  error?: ApiError | null;
  onRetry?: () => void;
  emptyMessage?: string;
}

export function DataTable<T>({ columns, rows, rowKey, isLoading, error, onRetry, emptyMessage }: DataTableProps<T>) {
  if (isLoading) {
    return (
      <div className={styles.wrapper}>
        <div className={styles.statusCell}>
          <Spinner label="Loading data…" fullPage />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.wrapper}>
        <div className={styles.statusCell}>
          <ErrorBox error={error} onRetry={onRetry} />
        </div>
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div className={styles.wrapper}>
        <div className={styles.statusCell}>
          <EmptyState icon="chest" title="Nothing here yet" message={emptyMessage ?? 'No records to show.'} />
        </div>
      </div>
    );
  }

  return (
    <div className={styles.wrapper}>
      <table className={styles.table}>
        <thead>
          <tr>
            {columns.map((col, i) => (
              <th key={col.key} scope="col" className={i === 0 ? styles.sticky : undefined} style={col.align === 'right' ? { textAlign: 'right' } : undefined}>
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((col, i) => (
                <td key={col.key} className={i === 0 ? styles.sticky : undefined} style={col.align === 'right' ? { textAlign: 'right' } : undefined}>
                  {col.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
