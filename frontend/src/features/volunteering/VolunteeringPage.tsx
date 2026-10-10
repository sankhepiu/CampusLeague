import { Link } from 'react-router-dom';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { EmptyState } from '../../components/EmptyState/EmptyState';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { ProgressBar } from '../../components/ProgressBar/ProgressBar';
import { Money } from '../../components/Money/Money';
import { useAsync } from '../../core/hooks/useAsync';
import { useAuth } from '../../core/hooks/useAuth';
import { accentVarForFeature } from '../../core/config/accents';
import { volunteeringApi } from './api';
import styles from './VolunteeringPage.module.scss';

export function VolunteeringPage() {
  const { hasRole } = useAuth();
  const { status, data, error, reload } = useAsync(() => volunteeringApi.listFundraisers(), []);
  const canManage = hasRole('president', 'volunteer_coordinator');

  return (
    <PageShell title="Volunteering">
      {canManage && (
        <div className={styles.header}>
          <Link to="/volunteering/new" className={styles.newButton}>
            + New Fundraiser
          </Link>
        </div>
      )}

      {status === 'loading' && <Spinner fullPage label="Loading fundraisers…" />}
      {status === 'error' && <ErrorBox error={error!} onRetry={reload} />}
      {status === 'success' && data.results.length === 0 && (
        <Panel>
          <EmptyState icon="trophy" title="No fundraisers yet" message="Check back once one is announced." />
        </Panel>
      )}

      {status === 'success' && data.results.length > 0 && (
        <div className={styles.grid}>
          {data.results.map((f) => (
            <Link key={f.id} to={`/volunteering/${f.id}`} className={styles.card}>
              <Panel accent={accentVarForFeature('volunteering')}>
                <h3 className={styles.title}>{f.title}</h3>
                <ProgressBar
                  percent={f.progress.raisedPct}
                  onTrack={f.progress.onTrack}
                  label={
                    <>
                      <Money paise={f.progress.raisedAmount} /> of <Money paise={f.progress.goalAmount} />
                    </>
                  }
                />
                <p className={styles.meta}>
                  {f.progress.tasksDone}/{f.progress.tasksTotal} tasks done
                </p>
              </Panel>
            </Link>
          ))}
        </div>
      )}
    </PageShell>
  );
}
