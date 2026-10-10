import type { FeatureKey } from './roles';

/** Returns the CSS var reference for a feature area's accent glow, as defined
 * in styles/_variables.scss (--cl-accent-<area>). */
export function accentVarForFeature(key: FeatureKey): string {
  return `var(--cl-accent-${key})`;
}
