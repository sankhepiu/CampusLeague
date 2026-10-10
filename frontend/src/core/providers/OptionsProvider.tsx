import { createContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useLocalStorageState } from '../hooks/useLocalStorageState';

export interface Options {
  muted: boolean;
  volume: number; // 0..1
  reducedMotion: boolean;
}

interface OptionsContextValue {
  options: Options;
  toggleMuted: () => void;
  setVolume: (volume: number) => void;
  toggleReducedMotion: () => void;
}

const DEFAULT_OPTIONS: Options = { muted: false, volume: 0.6, reducedMotion: false };

export const OptionsContext = createContext<OptionsContextValue | null>(null);

export function OptionsProvider({ children }: { children: ReactNode }) {
  const [options, setOptions] = useLocalStorageState<Options>('campusleague.options', DEFAULT_OPTIONS);
  const [osReducedMotion, setOsReducedMotion] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  );

  useEffect(() => {
    const mql = window.matchMedia('(prefers-reduced-motion: reduce)');
    const onChange = () => setOsReducedMotion(mql.matches);
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, []);

  // Mirrored onto <html> so any CSS animation/transition app-wide can be
  // killed with one selector (see styles/global.scss), honoring both the
  // in-app toggle and the OS-level `prefers-reduced-motion` setting.
  useEffect(() => {
    document.documentElement.dataset.reducedMotion = String(options.reducedMotion || osReducedMotion);
  }, [options.reducedMotion, osReducedMotion]);

  const value = useMemo<OptionsContextValue>(
    () => ({
      options,
      toggleMuted: () => setOptions((o) => ({ ...o, muted: !o.muted })),
      setVolume: (volume) => setOptions((o) => ({ ...o, volume: Math.min(1, Math.max(0, volume)) })),
      toggleReducedMotion: () => setOptions((o) => ({ ...o, reducedMotion: !o.reducedMotion })),
    }),
    [options, setOptions],
  );

  return <OptionsContext.Provider value={value}>{children}</OptionsContext.Provider>;
}
