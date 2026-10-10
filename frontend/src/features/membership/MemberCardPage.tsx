import { Link } from 'react-router-dom';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { EmptyState } from '../../components/EmptyState/EmptyState';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { StatusBadge } from '../../components/StatusBadge/StatusBadge';
import { QRCode } from '../../components/QRCode/QRCode';
import { useAsync } from '../../core/hooks/useAsync';
import { useAuth } from '../../core/hooks/useAuth';
import { accentVarForFeature } from '../../core/config/accents';
import { membershipApi } from './api';
import { formatDate, daysUntil } from './dates';
import styles from './MemberCardPage.module.scss';

const RENEWAL_WINDOW_DAYS = 30;

export function MemberCardPage() {
  const { user } = useAuth();
  const { status, data, error, reload } = useAsync(() => membershipApi.getMyMembership(), []);

  return (
    <PageShell title="Member Card" background="dotted">
      {status === 'loading' && <Spinner fullPage label="Loading your card…" />}
      {status === 'error' && <ErrorBox error={error!} onRetry={reload} />}

      {/* No token means this person has never been a member. */}
      {status === 'success' && !data.memberQrToken && (
        <Panel>
          <EmptyState
            icon="chest"
            title="Join to get your card"
            message="Buy a membership plan and your member card, with its QR code for the door, appears here."
            action={
              <Link to="/membership" style={{ textDecoration: 'none' }}>
                Browse Plans
              </Link>
            }
          />
        </Panel>
      )}

      {status === 'success' && data.memberQrToken && user && (
        <>
          {(data.status === 'lapsed' || (data.membership && daysUntil(data.membership.endDate) <= RENEWAL_WINDOW_DAYS)) && (
            <Panel accent="var(--cl-coral)" style={{ maxWidth: '26rem', margin: '0 auto 1.5rem' }}>
              <strong>{data.status === 'lapsed' ? 'Your membership has lapsed.' : 'Renewal reminder:'}</strong>{' '}
              {data.status === 'lapsed' || !data.membership
                ? 'Your card still scans, but as "not a member". Renew to restore your benefits.'
                : `Your membership ends ${formatDate(data.membership.endDate)}.`}{' '}
              <Link to="/membership">Renew now</Link>
            </Panel>
          )}

          <Panel accent={accentVarForFeature('membership')} className={styles.card}>
            <h2 className={styles.name}>{user.name}</h2>
            <div className={styles.statusRow}>
              <StatusBadge variant={data.status === 'active' ? 'success' : 'danger'}>{data.status === 'active' ? 'Active' : 'Lapsed'}</StatusBadge>
            </div>

            <div className={styles.qrWrap}>
              <QRCode value={data.memberQrToken} size={200} />
            </div>
            <p className={styles.scanHint}>Show this code at the door. Staff scan it to confirm your membership.</p>

            {data.membership && (
              <>
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
              </>
            )}
          </Panel>
        </>
      )}
    </PageShell>
  );
}
