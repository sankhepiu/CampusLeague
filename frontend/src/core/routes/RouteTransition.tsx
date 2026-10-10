import type { ReactNode } from 'react';
import { useLocation } from 'react-router-dom';

/** Wraps routed content in a short fade-and-rise that replays on every
 * navigation (keyed on the router location so React remounts it). The
 * animation itself is defined once in styles/global.scss and is neutralized
 * app-wide by the reduced-motion CSS rule there, so no extra gating is
 * needed here. */
export function RouteTransition({ children }: { children: ReactNode }) {
  const location = useLocation();
  return (
    <div key={location.pathname} className="cl-route-transition">
      {children}
    </div>
  );
}
