import { Link, useParams } from 'react-router-dom';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { StatusBadge, type StatusBadgeVariant } from '../../components/StatusBadge/StatusBadge';
import { QRCode } from '../../components/QRCode/QRCode';
import { useAsync } from '../../core/hooks/useAsync';
import { accentVarForFeature } from '../../core/config/accents';
import { formatDateTime } from '../../core/utils/formatDateTime';
import { ticketsApi } from './api';
import type { TicketStatus } from './types';
import styles from './PassDetailPage.module.scss';

const STATUS_LABEL: Record<TicketStatus, string> = { valid: 'Valid', checked_in: 'Checked In', cancelled: 'Cancelled' };
const STATUS_VARIANT: Record<TicketStatus, StatusBadgeVariant> = { valid: 'success', checked_in: 'info', cancelled: 'danger' };

export function PassDetailPage() {
  const { id } = useParams<{ id: string }>();
  const passId = Number(id);
  const { status, data: pass, error, reload } = useAsync(() => ticketsApi.getPass(passId), [passId]);

  if (status === 'loading') return <Spinner fullPage label="Loading pass…" />;
  if (status === 'error') return <ErrorBox error={error!} onRetry={reload} />;
  if (!pass) return null;

  return (
    <PageShell title={pass.event.title}>
      <Link to="/tickets" className={styles.backLink}>
        ← Back to My Tickets
      </Link>

      <Panel accent={accentVarForFeature('tickets')} className={styles.summaryPanel}>
        <div className={styles.summaryRow}>
          <div>
            <p className={styles.meta}>{formatDateTime(pass.event.startsAt)}</p>
            <p className={styles.meta}>{pass.event.venue}</p>
            <p className={styles.meta}>{pass.tier.name}</p>
            <p className={styles.meta}>Held by {pass.holder.name}</p>
          </div>
          <StatusBadge variant={pass.remaining === 0 ? 'neutral' : pass.admitted > 0 ? 'info' : 'success'}>
            Admitted {pass.admitted} / {pass.quantity}
          </StatusBadge>
        </div>

        <div className={styles.qrRow}>
          <QRCode value={pass.qrToken} size={160} />
          <p className={styles.qrNote}>
            One QR admits the next unused seat on this pass — {pass.remaining} remaining of {pass.quantity}.
          </p>
        </div>
      </Panel>

      <h3 className={styles.sectionTitle}>Seats</h3>
      <div className={styles.ticketList}>
        {pass.tickets.map((t) => (
          <Panel key={t.id} className={styles.ticketRow}>
            <span className={styles.ticketCode}>{t.code}</span>
            <StatusBadge variant={STATUS_VARIANT[t.status]}>{STATUS_LABEL[t.status]}</StatusBadge>
          </Panel>
        ))}
      </div>

      <h3 className={styles.sectionTitle}>Check-in History</h3>
      {pass.history.length === 0 ? (
        <p className={styles.meta}>No one has been admitted on this pass yet.</p>
      ) : (
        <div className={styles.historyList}>
          {pass.history.map((h, i) => (
            <Panel key={i} className={styles.historyRow}>
              <span>
                {h.count} admitted by {h.by}
              </span>
              <span className={styles.meta}>{formatDateTime(h.at)}</span>
            </Panel>
          ))}
        </div>
      )}
    </PageShell>
  );
}
