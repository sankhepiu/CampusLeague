export interface AchievementDef {
  id: string;
  title: string;
  description: string;
}

/** Neutral, campus-themed achievements for Phase 0. More will be added as real
 * features (events, volunteering, etc.) ship. */
export const ACHIEVEMENTS: AchievementDef[] = [
  { id: 'welcome', title: 'Welcome Aboard', description: 'Booted up Campus League for the first time.' },
  { id: 'role_explorer', title: 'Role Explorer', description: 'Reached your personalized home dashboard.' },
  { id: 'tinkerer', title: 'Tinkerer', description: 'Changed a setting in Options.' },
];

export const ACHIEVEMENTS_BY_ID: Record<string, AchievementDef> = Object.fromEntries(
  ACHIEVEMENTS.map((a) => [a.id, a]),
);
