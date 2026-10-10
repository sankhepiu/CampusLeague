import { useState } from 'react';
import { Link } from 'react-router-dom';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { EmptyState } from '../../components/EmptyState/EmptyState';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { Money } from '../../components/Money/Money';
import { StatusBadge } from '../../components/StatusBadge/StatusBadge';
import { useAsync } from '../../core/hooks/useAsync';
import { useAuth } from '../../core/hooks/useAuth';
import { accentVarForFeature } from '../../core/config/accents';
import { formatDateTime } from '../../core/utils/formatDateTime';
import { eventsApi } from './api';
import styles from './EventsPage.module.scss';

export function EventsPage() {
  const { hasRole } = useAuth();
  const [page, setPage] = useState(1);
  const { status, data, error, reload } = useAsync(() => eventsApi.list(page), [page]);

  const canManage = hasRole('president', 'event_manager');

  return (
    <PageShell title="Events">
      {canManage && (
        <div className={styles.header}>
          <Link to="/events/new" className={styles.newButton}>
            + New Event
          </Link>
        </div>
      )}

      {status === 'loading' && <Spinner fullPage label="Loading events…" />}
      {status === 'error' && <ErrorBox error={error!} onRetry={reload} />}
      {status === 'success' && data.results.length === 0 && (
        <Panel>
          <EmptyState icon="trophy" title="No events yet" message="Check back once events are published." />
        </Panel>
      )}

      {status === 'success' && data.results.length > 0 && (
        <>
          <div className={styles.grid}>
            {data.results.map((event) => {
              const cheapest = event.tiers[0];
              const soldOut = event.tiers.length > 0 && event.tiers.every((t) => t.seatsLeft === 0);
              return (
                <Link key={event.id} to={`/events/${event.id}`} className={styles.card}>
                  <Panel accent={accentVarForFeature('events')}>
                    <h3 className={styles.eventTitle}>{event.title}</h3>
                    <p className={styles.meta}>{formatDateTime(event.startsAt)}</p>
                    <p className={styles.meta}>{event.venue}</p>
                    <div className={styles.statusRow}>
                      <StatusBadge variant={event.status === 'on_sale' ? 'success' : event.status === 'draft' ? 'warning' : 'neutral'}>
                        {event.status.replace('_', ' ')}
                      </StatusBadge>
                    </div>
                    {cheapest && (
                      <div className={styles.priceRow}>
                        <span>{soldOut ? 'Sold out' : 'From'}</span>
                        {!soldOut && <Money paise={cheapest.price} />}
                      </div>
                    )}
                  </Panel>
                </Link>
              );
            })}
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
