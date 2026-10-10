import { useEffect } from 'react';
import { Panel } from '../../components/Panel/Panel';
import { EmptyState } from '../../components/EmptyState/EmptyState';
import { TiltCard } from '../../components/TiltCard/TiltCard';
import { useAuth } from '../hooks/useAuth';
import { useAchievements } from '../hooks/useAchievements';
import { navItemsForRoles } from './navItems';
import { ROLE_LABELS } from '../config/roles';
import { accentVarForFeature } from '../config/accents';
import styles from './HomePage.module.scss';

export function HomePage() {
  const { user } = useAuth();
  const { unlock } = useAchievements();

  useEffect(() => {
    unlock('role_explorer');
  }, [unlock]);

  if (!user) return null;
  const items = navItemsForRoles(user.roles);
  // An ordinary signed-up user has no committee role at all (roles: []) —
  // being a paid-up member is tracked separately via membershipStatus.
  const dashboardTitle = user.roles[0] ? ROLE_LABELS[user.roles[0]] : 'Member';

  return (
    <div className={styles.wrapper}>
      <p className={styles.greeting}>Welcome back, {user.name.split(' ')[0]}</p>
      <h1 className={styles.title}>{dashboardTitle} Dashboard</h1>

      {items.length === 0 ? (
        <Panel>
          <EmptyState
            icon="ghost"
            title="Nothing to show yet"
            message="Your role doesn't have any features assigned yet. Check back once your club admin sets things up."
          />
        </Panel>
      ) : (
        <div className={styles.grid}>
          {items.map((item) => (
            <TiltCard key={item.path} to={item.path} icon={item.icon} label={item.label} accent={accentVarForFeature(item.key)} />
          ))}
        </div>
      )}
    </div>
  );
}
