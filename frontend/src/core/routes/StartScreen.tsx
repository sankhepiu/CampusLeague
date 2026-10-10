import { useNavigate } from 'react-router-dom';
import { Coin3D } from '../../components/Coin3D/Coin3D';
import { useSound } from '../hooks/useSound';
import { useAchievements } from '../hooks/useAchievements';
import { usePrefersReducedMotion } from '../hooks/usePrefersReducedMotion';
import styles from './StartScreen.module.scss';

export function StartScreen() {
  const navigate = useNavigate();
  const { playSound } = useSound();
  const { unlock } = useAchievements();
  const reducedMotion = usePrefersReducedMotion();

  const start = () => {
    playSound('confirm');
    unlock('welcome');
    navigate('/loading');
  };

  return (
    <div className={`${styles.screen} ${reducedMotion ? styles.flat : ''}`}>
      {!reducedMotion && (
        <div className={styles.floorStage} aria-hidden="true">
          <div className={styles.floor} />
          <div className={styles.horizon} />
        </div>
      )}

      <div className={styles.content}>
        <Coin3D size={72} />
        <h1 className={styles.title}>Campus League</h1>
        <p className={styles.subtitle}>Your clubs. Your events. Your campus, gamified.</p>
        <button type="button" className={styles.startButton} onClick={start} autoFocus>
          Press Start
        </button>
        <p className={styles.hint}>Press Enter or click to begin</p>
      </div>
    </div>
  );
}
