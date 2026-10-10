import { Panel } from '../Panel/Panel';
import { EmptyState } from '../EmptyState/EmptyState';
import { PageShell } from '../PageShell/PageShell';
import type { PixelIconName } from '../PixelIcon';
import { accentVarForFeature } from '../../core/config/accents';
import type { FeatureKey } from '../../core/config/roles';

interface FeatureComingSoonProps {
  title: string;
  description: string;
  icon?: PixelIconName;
  area: FeatureKey;
}

/** Placeholder rendered by each feature's index page until real screens ship.
 * Glows in the area's own accent color (see styles/_variables.scss). */
export function FeatureComingSoon({ title, description, icon = 'chest', area }: FeatureComingSoonProps) {
  return (
    <PageShell title={title}>
      <Panel accent={accentVarForFeature(area)}>
        <EmptyState icon={icon} title="Coming Soon" message={description} />
      </Panel>
    </PageShell>
  );
}
