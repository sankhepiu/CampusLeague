import { useEffect } from 'react';
import { Panel } from '../../components/Panel/Panel';
import { EmptyState } from '../../components/EmptyState/EmptyState';
import { TiltCard } from '../../components/TiltCard/TiltCard';
import { useAuth } from '../hooks/useAuth';
import { useAchievements } from '../hooks/useAchievements';
import { navItemsForRoles } from './navItems';
import { MY_ACCOUNT_TOOLS, toolsForRoles } from './dashboardTools';
import { ROLE_LABELS } from '../config/roles';
import { accentVarForFeature } from '../config/accents';
import styles from './HomePage.module.scss';

// The Django admin account is seeded with no club roles, same as a brand
// new member — the only thing that actually tells them apart is this
// specific, known demo email, so that's what we key off.
const DJANGO_ADMIN_EMAIL = 'admin@skyline.test';

export function HomePage() {
  const { user } = useAuth();
  const { unlock } = useAchievements();

  useEffect(() => {
    unlock('role_explorer');
  }, [unlock]);

  if (!user) return null;

  if (user.roles.length === 0 && user.email.toLowerCase() === DJANGO_ADMIN_EMAIL) {
    return (
      <div className={styles.wrapper}>
        <h1 className={styles.title}>Backend Admin Account</h1>
        <Panel>
          <EmptyState
            icon="ghost"
            title="This is the backend admin account"
            message="Manage data at http://127.0.0.1:8000/admin — this account has no club roles and nothing to do on the member side of the app."
          />
        </Panel>
      </div>
    );
  }

  const roleTools = toolsForRoles(user.roles);
  // An ordinary signed-up user has no committee role at all (roles: []) —
  // being a paid-up member is tracked separately via membershipStatus.
  const dashboardTitle = user.roles[0] ? ROLE_LABELS[user.roles[0]] : 'Member';

  // Staff (anyone with at least one committee role whose tools we know)
  // get a focused dashboard: their own tools first, then My Account.
  // A plain member keeps the original full nav grid — Events/Shop/
  // Volunteering/Announcements have nowhere else to live for them.
  if (roleTools.length > 0) {
    return (
      <div className={styles.wrapper}>
        <p className={styles.greeting}>Welcome back, {user.name.split(' ')[0]}</p>
        <h1 className={styles.title}>{dashboardTitle} Dashboard</h1>

        <div className={styles.section}>
          <h2 className={styles.sectionTitle}>{dashboardTitle} Tools</h2>
          <div className={styles.grid}>
            {roleTools.map((tool) => (
              <TiltCard key={tool.key} to={tool.path} icon={tool.icon} label={tool.label} accent={accentVarForFeature(tool.accentKey)} />
            ))}
          </div>
        </div>
        <div className={styles.section}>
          <h2 className={styles.sectionTitle}>My Account</h2>
          <div className={styles.grid}>
            {MY_ACCOUNT_TOOLS.map((tool) => (
              <TiltCard key={tool.key} to={tool.path} icon={tool.icon} label={tool.label} accent={accentVarForFeature(tool.accentKey)} />
            ))}
          </div>
        </div>
      </div>
    );
  }

  const items = navItemsForRoles(user.roles);

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
