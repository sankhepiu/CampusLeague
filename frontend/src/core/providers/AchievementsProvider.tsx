import { createContext, useCallback, useMemo, useRef, useState, type ReactNode } from 'react';
import { ACHIEVEMENTS_BY_ID, type AchievementDef } from '../config/achievements';
import { useLocalStorageState } from '../hooks/useLocalStorageState';
import { useSound } from '../hooks/useSound';
import { FanfareOverlay } from '../../components/Fanfare/FanfareOverlay';

interface AchievementsContextValue {
  unlockedIds: string[];
  isUnlocked: (id: string) => boolean;
  unlock: (id: string) => void;
}

export const AchievementsContext = createContext<AchievementsContextValue | null>(null);

export function AchievementsProvider({ children }: { children: ReactNode }) {
  const [unlockedIds, setUnlockedIds] = useLocalStorageState<string[]>('campusleague.achievements', []);
  // Multiple achievements can unlock in the same tick (e.g. on first boot), so
  // queue them and show the fanfare one at a time rather than clobbering.
  const [queue, setQueue] = useState<AchievementDef[]>([]);
  const { playSound } = useSound();

  // Mirrors unlockedIds but updated synchronously, so a single unlock() call
  // can never fire its side effects twice — React 19 Strict Mode intentionally
  // double-invokes setState updater functions (and effects), which would
  // otherwise double-queue the fanfare if the guard lived inside setState.
  const unlockedRef = useRef(new Set(unlockedIds));

  const isUnlocked = useCallback((id: string) => unlockedIds.includes(id), [unlockedIds]);

  const unlock = useCallback(
    (id: string) => {
      const def = ACHIEVEMENTS_BY_ID[id];
      if (!def || unlockedRef.current.has(id)) return;
      unlockedRef.current.add(id);
      playSound('achievement');
      setQueue((q) => [...q, def]);
      setUnlockedIds((prev) => (prev.includes(id) ? prev : [...prev, id]));
    },
    [playSound, setUnlockedIds],
  );

  const value = useMemo<AchievementsContextValue>(() => ({ unlockedIds, isUnlocked, unlock }), [unlockedIds, isUnlocked, unlock]);

  return (
    <AchievementsContext.Provider value={value}>
      {children}
      <FanfareOverlay achievement={queue[0] ?? null} onDone={() => setQueue((q) => q.slice(1))} />
    </AchievementsContext.Provider>
  );
}
