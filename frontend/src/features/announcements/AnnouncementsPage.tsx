import { useState } from 'react';
import { Link } from 'react-router-dom';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { EmptyState } from '../../components/EmptyState/EmptyState';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { useAsync } from '../../core/hooks/useAsync';
import { useAuth } from '../../core/hooks/useAuth';
import { accentVarForFeature } from '../../core/config/accents';
import { announcementsApi } from './api';
import styles from './AnnouncementsPage.module.scss';
import { formatDateTime } from '../../core/utils/formatDateTime';

export function AnnouncementsPage() {
  const { hasRole } = useAuth();
  const [page, setPage] = useState(1);
  const { status, data, error, reload } = useAsync(() => announcementsApi.list(page), [page]);

  const canCompose = hasRole('president', 'event_manager', 'volunteer_coordinator');

  return (
    <PageShell title="Announcements" background="dotted">
      {canCompose && (
        <div className={styles.header}>
          <Link to="/announcements/new" className={styles.composeButton}>
            + New Announcement
          </Link>
        </div>
      )}

      {status === 'loading' && <Spinner fullPage label="Loading announcements…" />}
      {status === 'error' && <ErrorBox error={error!} onRetry={reload} />}
      {status === 'success' && data.results.length === 0 && (
        <Panel>
          <EmptyState icon="badge" title="No announcements yet" message="Check back soon." />
        </Panel>
      )}

      {status === 'success' && data.results.length > 0 && (
        <>
          <div className={styles.list}>
            {data.results.map((a) => (
              <Link key={a.id} to={`/announcements/${a.id}`} className={styles.card}>
                <Panel accent={accentVarForFeature('announcements')}>
                  <h3 className={styles.title}>{a.title}</h3>
                  <p className={styles.meta}>
                    {a.author.name} · {formatDateTime(a.publishedAt)} · {a.audience === 'members' ? 'Members only' : 'Everyone'}
                  </p>
                </Panel>
              </Link>
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
