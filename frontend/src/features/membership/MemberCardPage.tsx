import { Link } from 'react-router-dom';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { EmptyState } from '../../components/EmptyState/EmptyState';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { StatusBadge, type StatusBadgeVariant } from '../../components/StatusBadge/StatusBadge';
import { QRCode } from '../../components/QRCode/QRCode';
import { useAsync } from '../../core/hooks/useAsync';
import { useAuth } from '../../core/hooks/useAuth';
import { accentVarForFeature } from '../../core/config/accents';
import { membershipApi } from './api';
import { formatDate, daysUntil } from './dates';
import styles from './MemberCardPage.module.scss';

const RENEWAL_WINDOW_DAYS = 30;

const STATUS_LABEL: Record<'active' | 'lapsed' | 'pending' | 'cancelled', string> = {
  active: 'Active',
  lapsed: 'Lapsed',
  pending: 'Pending',
  cancelled: 'Cancelled',
};

const STATUS_VARIANT: Record<'active' | 'lapsed' | 'pending' | 'cancelled', StatusBadgeVariant> = {
  active: 'success',
  lapsed: 'danger',
  pending: 'warning',
  cancelled: 'neutral',
};

export function MemberCardPage() {
  const { user } = useAuth();
  const { status, data, error, reload } = useAsync(() => membershipApi.getMyMembership(), []);

  return (
    <PageShell title="Member Card" background="dotted">
      {status === 'loading' && <Spinner fullPage label="Loading your card…" />}
      {status === 'error' && <ErrorBox error={error!} onRetry={reload} />}

      {status === 'success' && !data.membership && (
        <Panel>
          <EmptyState
            icon="chest"
            title="No membership yet"
            message="Buy a plan to get your member card and check-in QR code."
            action={
              <Link to="/membership" style={{ textDecoration: 'none' }}>
                Browse Plans
              </Link>
            }
          />
        </Panel>
      )}

      {status === 'success' && data.membership && user && (
        <>
          {(data.membership.status === 'lapsed' || daysUntil(data.membership.endDate) <= RENEWAL_WINDOW_DAYS) && (
            <Panel accent="var(--cl-coral)" style={{ marginBottom: '1.5rem', maxWidth: '26rem', margin: '0 auto 1.5rem' }}>
              <strong>{data.membership.status === 'lapsed' ? 'Your membership has lapsed.' : 'Renewal reminder:'}</strong>{' '}
              {data.membership.status === 'lapsed'
                ? 'Renew to restore your benefits.'
                : `Your membership ends ${formatDate(data.membership.endDate)}.`}{' '}
              <Link to="/membership">Renew now</Link>
            </Panel>
          )}

          <Panel accent={accentVarForFeature('membership')} className={styles.card}>
            <h2 className={styles.name}>{user.name}</h2>
            <div className={styles.statusRow}>
              <StatusBadge variant={STATUS_VARIANT[data.membership.status]}>{STATUS_LABEL[data.membership.status]}</StatusBadge>
            </div>

            <div className={styles.qrWrap}>
              {data.membership.qrToken ? (
                <QRCode value={data.membership.qrToken} size={180} />
              ) : (
                <EmptyState icon="ghost" title="QR code not available" message="Check-in codes aren't issued by the server yet." />
              )}
            </div>

            <div className={styles.detail}>
              <span className={styles.detailLabel}>Plan</span>
              <span>{data.membership.plan.name}</span>
            </div>
            <div className={styles.detail}>
              <span className={styles.detailLabel}>Expires</span>
              <span>{formatDate(data.membership.endDate)}</span>
            </div>

            <ul className={styles.benefits}>
              <li>{data.membership.plan.ticketDiscountPct}% off event tickets</li>
              <li>{data.membership.plan.merchDiscountPct}% off merch</li>
            </ul>
          </Panel>
        </>
      )}
    </PageShell>
  );
}
