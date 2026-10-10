import { PixelIcon } from '../PixelIcon';
import { usePrefersReducedMotion } from '../../core/hooks/usePrefersReducedMotion';
import styles from './Coin3D.module.scss';

interface Coin3DProps {
  size?: number;
}

/** A rotating, bobbing pixel coin built from the flat `coin` PixelIcon with
 * real CSS 3D (rotateY on a preserve-3d element, two faces for the flip),
 * plus a soft glow beneath it. Falls back to a motionless flat coin when
 * reduced motion is requested — see usePrefersReducedMotion. */
export function Coin3D({ size = 72 }: Coin3DProps) {
  const reducedMotion = usePrefersReducedMotion();
  const bobClass = reducedMotion ? '' : styles.bob;
  const spinClass = reducedMotion ? '' : styles.spin;

  return (
    <div className={`${styles.wrap} ${reducedMotion ? styles.flat : ''}`}>
      <div className={bobClass}>
        <div className={spinClass}>
          <div className={styles.face}>
            <PixelIcon name="coin" size={size} />
          </div>
          {!reducedMotion && (
            <div className={`${styles.face} ${styles.back}`}>
              <PixelIcon name="coin" size={size} />
            </div>
          )}
        </div>
      </div>
      <div className={styles.glow} aria-hidden="true" />
    </div>
  );
}
