import { useState } from 'react';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { EmptyState } from '../../components/EmptyState/EmptyState';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { Money } from '../../components/Money/Money';
import { StatusBadge, type StatusBadgeVariant } from '../../components/StatusBadge/StatusBadge';
import { QRCode } from '../../components/QRCode/QRCode';
import { useAsync } from '../../core/hooks/useAsync';
import { accentVarForFeature } from '../../core/config/accents';
import { formatDateTime } from '../../core/utils/formatDateTime';
import { ticketsApi } from './api';
import type { Ticket, TicketStatus } from './types';
import styles from './TicketsPage.module.scss';

const STATUS_LABEL: Record<TicketStatus, string> = { valid: 'Valid', checked_in: 'Checked In', cancelled: 'Cancelled' };
const STATUS_VARIANT: Record<TicketStatus, StatusBadgeVariant> = { valid: 'success', checked_in: 'info', cancelled: 'danger' };

export function TicketsPage() {
  const [page, setPage] = useState(1);
  const { status, data, error, reload } = useAsync(() => ticketsApi.listMine(page), [page]);
  const [showToScanner, setShowToScanner] = useState<Ticket | null>(null);

  return (
    <PageShell title="My Tickets" background="dotted">
      {status === 'loading' && <Spinner fullPage label="Loading your tickets…" />}
      {status === 'error' && <ErrorBox error={error!} onRetry={reload} />}
      {status === 'success' && data.results.length === 0 && (
        <Panel>
          <EmptyState icon="chest" title="No tickets yet" message="Buy a ticket from an event page to see it here." />
        </Panel>
      )}

      {status === 'success' && data.results.length > 0 && (
        <>
          <div className={styles.list}>
            {data.results.map((ticket) => (
              <Panel key={ticket.id} accent={accentVarForFeature('tickets')}>
                <div className={styles.row}>
                  <div>
                    <h3 className={styles.eventTitle}>{ticket.event.title}</h3>
                    <p className={styles.meta}>{formatDateTime(ticket.event.startsAt)}</p>
                    <p className={styles.meta}>{ticket.event.venue}</p>
                    <p className={styles.meta}>{ticket.tier.name}</p>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <StatusBadge variant={STATUS_VARIANT[ticket.status]}>{STATUS_LABEL[ticket.status]}</StatusBadge>
                    <p className={styles.price}>
                      <Money paise={ticket.pricePaid} />
                    </p>
                  </div>
                </div>

                <div className={styles.row} style={{ marginTop: '1rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <QRCode value={ticket.qrToken} size={72} />
                    <span className={styles.meta}>{ticket.code}</span>
                  </div>
                  {ticket.status === 'valid' && (
                    <button type="button" className={styles.showButton} onClick={() => setShowToScanner(ticket)}>
                      Show to Scanner
                    </button>
                  )}
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

      {showToScanner && (
        <div className={styles.scannerOverlay} role="dialog" aria-modal="true" aria-label="Ticket QR code">
          <div className={styles.scannerCard}>
            <h2 className={styles.scannerTitle}>{showToScanner.event.title}</h2>
            <div className={styles.scannerQr}>
              <QRCode value={showToScanner.qrToken} size={260} />
            </div>
            <p className={styles.scannerCode}>{showToScanner.code}</p>
            <p className={styles.scannerMeta}>{showToScanner.tier.name}</p>
            <button type="button" className={styles.closeButton} onClick={() => setShowToScanner(null)}>
              Close
            </button>
          </div>
        </div>
      )}
    </PageShell>
  );
}
