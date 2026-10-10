import { useEffect, useState } from 'react';
import { useOptions } from './useOptions';

function osPrefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/** True when either the OS-level `prefers-reduced-motion` media query or the
 * app's own Options toggle asks for reduced motion — the single source of
 * truth 3D/animated components check before doing anything fancy. */
export function usePrefersReducedMotion(): boolean {
  const { options } = useOptions();
  const [osReduced, setOsReduced] = useState(osPrefersReducedMotion);

  useEffect(() => {
    const mql = window.matchMedia('(prefers-reduced-motion: reduce)');
    const onChange = () => setOsReduced(mql.matches);
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, []);

  return options.reducedMotion || osReduced;
}
