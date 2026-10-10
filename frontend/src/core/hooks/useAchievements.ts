import { useContext } from 'react';
import { AchievementsContext } from '../providers/AchievementsProvider';

export function useAchievements() {
  const ctx = useContext(AchievementsContext);
  if (!ctx) throw new Error('useAchievements must be used within an AchievementsProvider');
  return ctx;
}
