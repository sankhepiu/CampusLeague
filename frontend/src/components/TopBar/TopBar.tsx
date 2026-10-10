import { NavLink } from 'react-router-dom';
import { useAuth } from '../../core/hooks/useAuth';
import { useOptions } from '../../core/hooks/useOptions';
import { useSound } from '../../core/hooks/useSound';
import { useAchievements } from '../../core/hooks/useAchievements';
import { navItemsForRoles } from '../../core/routes/navItems';
import { PixelIcon } from '../PixelIcon';
import styles from './TopBar.module.scss';

export function TopBar() {
  const { user, logout } = useAuth();
  const { options, toggleMuted, toggleReducedMotion } = useOptions();
  const { playSound } = useSound();
  const { unlock } = useAchievements();

  if (!user) return null;
  const items = navItemsForRoles(user.roles);

  return (
    <header className={styles.bar}>
      <NavLink to="/home" className={styles.brand}>
        <PixelIcon name="coin" size={22} />
        Campus League
      </NavLink>

      <nav className={styles.nav}>
        {items.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) => `${styles.navLink} ${isActive ? styles.navLinkActive : ''}`}
            onClick={() => playSound('select')}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className={styles.controls}>
        <span className={styles.userBadge}>{user.name}</span>
        <button
          type="button"
          className={styles.iconButton}
          onClick={() => {
            toggleMuted();
            playSound('select');
          }}
          aria-pressed={options.muted}
          aria-label={options.muted ? 'Unmute sound' : 'Mute sound'}
          title={options.muted ? 'Unmute sound' : 'Mute sound'}
        >
          {options.muted ? '🔇' : '🔊'}
        </button>
        <button
          type="button"
          className={styles.iconButton}
          onClick={() => {
            toggleReducedMotion();
            unlock('tinkerer');
            playSound('confirm');
          }}
          aria-pressed={options.reducedMotion}
          aria-label="Toggle reduced motion"
          title="Toggle reduced motion"
        >
          ⚙
        </button>
        <button
          type="button"
          className={styles.logout}
          onClick={() => {
            playSound('cancel');
            logout();
          }}
        >
          Log Out
        </button>
      </div>
    </header>
  );
}
