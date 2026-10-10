import { useRef, type CSSProperties, type MouseEvent } from 'react';
import { Link } from 'react-router-dom';
import { PixelIcon, type PixelIconName } from '../PixelIcon';
import { useFinePointer } from '../../core/hooks/useFinePointer';
import { usePrefersReducedMotion } from '../../core/hooks/usePrefersReducedMotion';
import styles from './TiltCard.module.scss';

interface TiltCardProps {
  to: string;
  icon: PixelIconName;
  label: string;
  /** CSS color/var() reference for this card's glow, e.g. `var(--cl-accent-events)`. */
  accent?: string;
}

const MAX_TILT_DEG = 6;

/** A nav card that tilts a few degrees toward the cursor with a light sheen —
 * mouse/trackpad only (useFinePointer) and skipped entirely under reduced
 * motion. Tilt is applied by writing CSS custom properties straight to the
 * DOM node on pointer move rather than React state, so it never re-renders. */
export function TiltCard({ to, icon, label, accent }: TiltCardProps) {
  const finePointer = useFinePointer();
  const reducedMotion = usePrefersReducedMotion();
  const enableTilt = finePointer && !reducedMotion;
  const ref = useRef<HTMLAnchorElement>(null);

  const onMouseMove = (event: MouseEvent<HTMLAnchorElement>) => {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const px = (event.clientX - rect.left) / rect.width;
    const py = (event.clientY - rect.top) / rect.height;
    el.style.setProperty('--ry', `${(px - 0.5) * 2 * MAX_TILT_DEG}deg`);
    el.style.setProperty('--rx', `${(0.5 - py) * 2 * MAX_TILT_DEG}deg`);
    el.style.setProperty('--mx', `${px * 100}%`);
    el.style.setProperty('--my', `${py * 100}%`);
  };

  const onMouseLeave = () => {
    const el = ref.current;
    if (!el) return;
    el.style.setProperty('--rx', '0deg');
    el.style.setProperty('--ry', '0deg');
  };

  const style: CSSProperties | undefined = accent ? ({ '--panel-accent': accent } as CSSProperties) : undefined;

  return (
    <Link
      ref={ref}
      to={to}
      className={styles.card}
      style={style}
      onMouseMove={enableTilt ? onMouseMove : undefined}
      onMouseLeave={enableTilt ? onMouseLeave : undefined}
    >
      <PixelIcon name={icon} size={36} />
      <span className={styles.label}>{label}</span>
      {enableTilt && <span className={styles.sheen} aria-hidden="true" />}
    </Link>
  );
}
