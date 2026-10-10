import { useEffect, useState } from 'react';

function matches(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(hover: hover) and (pointer: fine)').matches;
}

/** True for mouse/trackpad input, false on touch — used to gate hover-only
 * flourishes like card tilt so they never fire (or linger) on touch devices. */
export function useFinePointer(): boolean {
  const [fine, setFine] = useState(matches);

  useEffect(() => {
    const mql = window.matchMedia('(hover: hover) and (pointer: fine)');
    const onChange = () => setFine(mql.matches);
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, []);

  return fine;
}
