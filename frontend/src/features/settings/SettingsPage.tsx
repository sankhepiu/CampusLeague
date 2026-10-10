import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { SelectInput } from '../../components/FormField/SelectInput';
import { Toggle } from '../../components/Toggle/Toggle';
import { useOptions } from '../../core/hooks/useOptions';
import { useAchievements } from '../../core/hooks/useAchievements';
import { FONT_CHOICES, FONT_LABELS, type FontChoice } from '../../core/providers/OptionsProvider';
import styles from './SettingsPage.module.scss';

/** Settings page — deliberately small: font choice and a sound toggle, and
 * nothing else (reduced-motion still auto-follows the OS preference, it just
 * has no manual control here). */
export function SettingsPage() {
  const { options, setFont, toggleMuted } = useOptions();
  const { unlock } = useAchievements();

  return (
    <PageShell title="Settings" background="dotted">
      <Panel accent="var(--cl-violet)">
        <div className={styles.section}>
          <h2 className={styles.sectionTitle}>Appearance</h2>
          <SelectInput
            label="Font"
            value={options.font}
            onChange={(e) => {
              setFont(e.target.value as FontChoice);
              unlock('tinkerer');
            }}
            options={FONT_CHOICES.map((choice) => ({ value: choice, label: FONT_LABELS[choice] }))}
          />
        </div>

        <div className={styles.section}>
          <h2 className={styles.sectionTitle}>Sound</h2>
          <Toggle
            label="Sound effects"
            checked={!options.muted}
            onChange={() => {
              toggleMuted();
              unlock('tinkerer');
            }}
          />
        </div>
      </Panel>
    </PageShell>
  );
}
