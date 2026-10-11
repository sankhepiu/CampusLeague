import { useState } from 'react';
import { Link } from 'react-router-dom';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { EmptyState } from '../../components/EmptyState/EmptyState';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { StatusBadge } from '../../components/StatusBadge/StatusBadge';
import { QRCode } from '../../components/QRCode/QRCode';
import { useAsync } from '../../core/hooks/useAsync';
import { accentVarForFeature } from '../../core/config/accents';
import { formatDateTime } from '../../core/utils/formatDateTime';
import { ticketsApi } from './api';
import type { Pass } from './types';
import styles from './TicketsPage.module.scss';

export function TicketsPage() {
  const [page, setPage] = useState(1);
  const { status, data, error, reload } = useAsync(() => ticketsApi.listMine(page), [page]);
  const [showToScanner, setShowToScanner] = useState<Pass | null>(null);

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
            {data.results.map((pass) => (
              <Panel key={pass.passId} accent={accentVarForFeature('tickets')}>
                <div className={styles.row}>
                  <div>
                    <h3 className={styles.eventTitle}>{pass.event.title}</h3>
                    <p className={styles.meta}>{formatDateTime(pass.event.startsAt)}</p>
                    <p className={styles.meta}>{pass.event.venue}</p>
                    <p className={styles.meta}>{pass.tier.name}</p>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <StatusBadge variant={pass.remaining === 0 ? 'neutral' : pass.admitted > 0 ? 'info' : 'success'}>
                      Admitted {pass.admitted} / {pass.quantity}
                    </StatusBadge>
                  </div>
                </div>

                <div className={styles.row} style={{ marginTop: '1rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <QRCode value={pass.qrToken} size={72} />
                    <span className={styles.meta}>
                      {pass.quantity} seat{pass.quantity === 1 ? '' : 's'} on this pass
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap' }}>
                    <Link to={`/tickets/${pass.passId}`} className={styles.detailLink}>
                      View Details
                    </Link>
                    {pass.remaining > 0 && (
                      <button type="button" className={styles.showButton} onClick={() => setShowToScanner(pass)}>
                        Show to Scanner
                      </button>
                    )}
                  </div>
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
        <div className={styles.scannerOverlay} role="dialog" aria-modal="true" aria-label="Pass QR code">
          <div className={styles.scannerCard}>
            <h2 className={styles.scannerTitle}>{showToScanner.event.title}</h2>
            <div className={styles.scannerQr}>
              <QRCode value={showToScanner.qrToken} size={260} />
            </div>
            <p className={styles.scannerCode}>
              Admitted {showToScanner.admitted} of {showToScanner.quantity}
            </p>
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
