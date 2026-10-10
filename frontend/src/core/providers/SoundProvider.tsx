import { createContext, useCallback, useEffect, useMemo, useRef, type ReactNode } from 'react';
import { useOptions } from '../hooks/useOptions';

export type SoundName = 'select' | 'confirm' | 'cancel' | 'achievement' | 'error';

/** Short 8-bit-style blips, synthesized with the Web Audio API so Phase 0 ships
 * with no audio asset files to source or license. Each note is a tiny square-wave
 * envelope; "achievement" chains three ascending notes for a fanfare feel. */
const NOTES: Record<SoundName, Array<{ freq: number; duration: number; delay: number }>> = {
  select: [{ freq: 440, duration: 0.05, delay: 0 }],
  confirm: [{ freq: 660, duration: 0.08, delay: 0 }],
  cancel: [{ freq: 220, duration: 0.08, delay: 0 }],
  error: [
    { freq: 180, duration: 0.09, delay: 0 },
    { freq: 140, duration: 0.12, delay: 0.09 },
  ],
  achievement: [
    { freq: 523, duration: 0.09, delay: 0 },
    { freq: 659, duration: 0.09, delay: 0.09 },
    { freq: 784, duration: 0.18, delay: 0.18 },
  ],
};

interface SoundContextValue {
  playSound: (name: SoundName) => void;
}

export const SoundContext = createContext<SoundContextValue | null>(null);

export function SoundProvider({ children }: { children: ReactNode }) {
  const { options } = useOptions();
  const ctxRef = useRef<AudioContext | null>(null);
  const optionsRef = useRef(options);
  useEffect(() => {
    optionsRef.current = options;
  }, [options]);

  const getContext = useCallback(() => {
    if (!ctxRef.current) {
      const AudioCtor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!AudioCtor) return null;
      ctxRef.current = new AudioCtor();
    }
    return ctxRef.current;
  }, []);

  const playSound = useCallback(
    (name: SoundName) => {
      const { muted, volume } = optionsRef.current;
      if (muted || volume <= 0) return;
      const audioCtx = getContext();
      if (!audioCtx) return;

      for (const note of NOTES[name]) {
        const oscillator = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        oscillator.type = 'square';
        oscillator.frequency.value = note.freq;
        const startAt = audioCtx.currentTime + note.delay;
        gain.gain.setValueAtTime(volume * 0.2, startAt);
        gain.gain.exponentialRampToValueAtTime(0.0001, startAt + note.duration);
        oscillator.connect(gain).connect(audioCtx.destination);
        oscillator.start(startAt);
        oscillator.stop(startAt + note.duration);
      }
    },
    [getContext],
  );

  const value = useMemo<SoundContextValue>(() => ({ playSound }), [playSound]);

  return <SoundContext.Provider value={value}>{children}</SoundContext.Provider>;
}
