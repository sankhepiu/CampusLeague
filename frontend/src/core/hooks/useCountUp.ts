import { useEffect, useRef, useState } from 'react';
import { usePrefersReducedMotion } from './usePrefersReducedMotion';

/** Animates a number from 0 to `target` over `durationMs`, easing out.
 * Under reduced motion, the target is returned directly at render time —
 * the rAF loop never starts, so there's nothing to animate or tear down. */
export function useCountUp(target: number, durationMs = 900): number {
  const reducedMotion = usePrefersReducedMotion();
  const [animatedValue, setAnimatedValue] = useState(0);
  const startRef = useRef<number | null>(null);

  useEffect(() => {
    if (reducedMotion) return;

    startRef.current = null;
    let frame: number;

    const tick = (timestamp: number) => {
      if (startRef.current === null) startRef.current = timestamp;
      const elapsed = timestamp - startRef.current;
      const progress = Math.min(1, elapsed / durationMs);
      const eased = 1 - (1 - progress) * (1 - progress);
      setAnimatedValue(Math.round(target * eased));
      if (progress < 1) frame = requestAnimationFrame(tick);
    };

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, durationMs, reducedMotion]);

  return reducedMotion ? target : animatedValue;
}
