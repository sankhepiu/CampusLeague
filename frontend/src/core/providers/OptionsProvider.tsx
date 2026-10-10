import { createContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useLocalStorageState } from '../hooks/useLocalStorageState';

export const FONT_CHOICES = ['pixelify', 'vt323', 'silkscreen'] as const;
export type FontChoice = (typeof FONT_CHOICES)[number];

export const FONT_LABELS: Record<FontChoice, string> = {
  pixelify: 'Pixelify Sans',
  vt323: 'VT323',
  silkscreen: 'Silkscreen',
};

export interface Options {
  muted: boolean;
  volume: number; // 0..1
  reducedMotion: boolean;
  font: FontChoice;
}

interface OptionsContextValue {
  options: Options;
  toggleMuted: () => void;
  setVolume: (volume: number) => void;
  toggleReducedMotion: () => void;
  setFont: (font: FontChoice) => void;
}

// Sound ships off by default — a student checking the app in a lecture hall
// shouldn't get an unexpected blip.
const DEFAULT_OPTIONS: Options = { muted: true, volume: 0.6, reducedMotion: false, font: 'pixelify' };

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

  // Mirrored onto <html> so global.scss can switch --cl-font-body per choice.
  useEffect(() => {
    document.documentElement.dataset.font = options.font;
  }, [options.font]);

  const value = useMemo<OptionsContextValue>(
    () => ({
      options,
      toggleMuted: () => setOptions((o) => ({ ...o, muted: !o.muted })),
      setVolume: (volume) => setOptions((o) => ({ ...o, volume: Math.min(1, Math.max(0, volume)) })),
      toggleReducedMotion: () => setOptions((o) => ({ ...o, reducedMotion: !o.reducedMotion })),
      setFont: (font) => setOptions((o) => ({ ...o, font })),
    }),
    [options, setOptions],
  );

  return <OptionsContext.Provider value={value}>{children}</OptionsContext.Provider>;
}
