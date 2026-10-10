import type { AchievementDef } from '../../core/config/achievements';
import { PixelIcon } from '../PixelIcon/PixelIcon';
import styles from './FanfareOverlay.module.scss';

interface FanfareOverlayProps {
  achievement: AchievementDef | null;
  onDone: () => void;
}

/** Full-screen celebration shown when an achievement unlocks. */
export function FanfareOverlay({ achievement, onDone }: FanfareOverlayProps) {
  if (!achievement) return null;

  return (
    <div className={styles.overlay} role="dialog" aria-modal="true" aria-label="Achievement unlocked">
      <div className={styles.card}>
        <p className={styles.eyebrow}>Achievement Unlocked</p>
        <PixelIcon name="badge" size={64} />
        <h2 className={styles.title}>{achievement.title}</h2>
        <p className={styles.description}>{achievement.description}</p>
        <button type="button" className={styles.dismiss} onClick={onDone} autoFocus>
          Nice!
        </button>
      </div>
    </div>
  );
}
