import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { PageShell } from '../../components/PageShell/PageShell';
import { DataTable, type DataTableColumn } from '../../components/DataTable/DataTable';
import { StatusBadge, type StatusBadgeVariant } from '../../components/StatusBadge/StatusBadge';
import { useAsync } from '../../core/hooks/useAsync';
import { announcementsApi } from './api';
import type { DeliveryLogEntry, DeliveryStatus } from './types';
import styles from './AnnouncementDeliveriesPage.module.scss';

const STATUS_VARIANT: Record<DeliveryStatus, StatusBadgeVariant> = { sent: 'success', queued: 'warning', failed: 'danger' };

const COLUMNS: DataTableColumn<DeliveryLogEntry>[] = [
  { key: 'name', header: 'Recipient', render: (d) => d.recipient.name },
  { key: 'email', header: 'Email', render: (d) => d.recipient.email },
  { key: 'status', header: 'Status', render: (d) => <StatusBadge variant={STATUS_VARIANT[d.status]}>{d.status}</StatusBadge> },
  { key: 'attempts', header: 'Attempts', render: (d) => d.attempts },
  { key: 'lastError', header: 'Last Error', render: (d) => d.lastError ?? '—' },
];

export function AnnouncementDeliveriesPage() {
  const { id } = useParams<{ id: string }>();
  const [page, setPage] = useState(1);
  const { status, data, error, reload } = useAsync(() => announcementsApi.listDeliveries(Number(id), page), [id, page]);

  return (
    <PageShell title="Delivery Log">
      <DataTable
        columns={COLUMNS}
        rows={data?.results ?? []}
        rowKey={(d) => String(d.id)}
        isLoading={status === 'loading'}
        error={error}
        onRetry={reload}
        emptyMessage="No delivery records for this announcement."
      />
      {data && (
        <div className={styles.pagination}>
          <button type="button" onClick={() => setPage((p) => p - 1)} disabled={!data.previous}>
            ← Previous
          </button>
          <button type="button" onClick={() => setPage((p) => p + 1)} disabled={!data.next}>
            Next →
          </button>
        </div>
      )}
    </PageShell>
  );
}
