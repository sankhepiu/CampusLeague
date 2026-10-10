import { Link, useParams } from 'react-router-dom';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { useAsync } from '../../core/hooks/useAsync';
import { accentVarForFeature } from '../../core/config/accents';
import { announcementsApi } from './api';
import styles from './AnnouncementDetailPage.module.scss';

export function AnnouncementDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { status, data: announcement, error, reload } = useAsync(() => announcementsApi.get(Number(id)), [id]);

  if (status === 'loading') return <Spinner fullPage label="Loading announcement…" />;
  if (status === 'error') return <ErrorBox error={error!} onRetry={reload} />;
  if (!announcement) return null;

  return (
    <PageShell title={announcement.title} background="dotted">
      <p className={styles.meta}>
        {announcement.author.name} · {new Date(announcement.publishedAt).toLocaleString('en-IN')} ·{' '}
        {announcement.audience === 'members' ? 'Members only' : 'Everyone'}
      </p>

      <p className={styles.body}>{announcement.body}</p>

      {announcement.deliveries && (
        <Panel accent={accentVarForFeature('announcements')}>
          <div className={styles.deliveryRow}>
            <span>{announcement.deliveries.recipients} recipients</span>
            <span>{announcement.deliveries.sent} sent</span>
            <span>{announcement.deliveries.queued} queued</span>
            <span>{announcement.deliveries.failed} failed</span>
          </div>
          <Link to={`/announcements/${announcement.id}/deliveries`} className={styles.logLink}>
            View Delivery Log
          </Link>
        </Panel>
      )}
    </PageShell>
  );
}
