import { useState } from 'react';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { EmptyState } from '../../components/EmptyState/EmptyState';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { Money } from '../../components/Money/Money';
import { StatusBadge, type StatusBadgeVariant } from '../../components/StatusBadge/StatusBadge';
import { useAsync } from '../../core/hooks/useAsync';
import { accentVarForFeature } from '../../core/config/accents';
import { formatDateTime } from '../../core/utils/formatDateTime';
import { ordersApi } from './api';
import type { Order, OrderKind, OrderStatus } from './types';
import styles from './OrdersPage.module.scss';

const STATUS_VARIANT: Record<OrderStatus, StatusBadgeVariant> = { paid: 'success', pending: 'warning', cancelled: 'danger' };
const KIND_LABEL: Record<OrderKind, string> = { membership: 'Membership', ticket: 'Ticket', merch: 'Merch' };

/** The server writes each line's `label` ("Spring Gala · General"); this
 * only adds the quantity when more than one was bought. */
function lineLabel(line: Order['lines'][number]): string {
  return line.qty > 1 ? `${line.label} × ${line.qty}` : line.label;
}

export function OrdersPage() {
  const [page, setPage] = useState(1);
  const { status, data, error, reload } = useAsync(() => ordersApi.listMine(page), [page]);

  return (
    <PageShell title="My Orders" background="dotted">
      {status === 'loading' && <Spinner fullPage label="Loading your orders…" />}
      {status === 'error' && <ErrorBox error={error!} onRetry={reload} />}
      {status === 'success' && data.results.length === 0 && (
        <Panel>
          <EmptyState icon="chest" title="No orders yet" message="Memberships, tickets and shop purchases will show up here." />
        </Panel>
      )}

      {status === 'success' && data.results.length > 0 && (
        <>
          <div className={styles.list}>
            {data.results.map((order) => (
              <Panel key={order.id} accent={accentVarForFeature('orders')}>
                <div className={styles.header}>
                  <span className={styles.orderMeta}>
                    Order #{order.id} · {formatDateTime(order.createdAt)}
                  </span>
                  <StatusBadge variant={STATUS_VARIANT[order.status]}>{order.status}</StatusBadge>
                </div>

                <ul className={styles.lines}>
                  {order.lines.map((line) => (
                    <li key={line.id} className={styles.line}>
                      <span>
                        <span className={styles.lineKind}>{KIND_LABEL[line.kind]}</span>
                        {lineLabel(line)}
                      </span>
                      <Money paise={line.qty * line.unitPrice - line.discount} />
                    </li>
                  ))}
                </ul>

                <div className={styles.totals}>
                  <span>
                    Subtotal <Money paise={order.subtotal} />
                  </span>
                  <span>
                    Discount <Money paise={order.discount} />
                  </span>
                  <strong>
                    Total <Money paise={order.total} />
                  </strong>
                </div>
              </Panel>
            ))}
          </div>

          <div className={styles.pagination}>
            <button type="button" className={styles.pageButton} onClick={() => setPage((p) => p - 1)} disabled={!data.previous}>
              ← Previous
            </button>
            <button type="button" className={styles.pageButton} onClick={() => setPage((p) => p + 1)} disabled={!data.next}>
              Next →
            </button>
          </div>
        </>
      )}
    </PageShell>
  );
}
