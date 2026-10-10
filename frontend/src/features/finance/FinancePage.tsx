import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { EmptyState } from '../../components/EmptyState/EmptyState';
import { accentVarForFeature } from '../../core/config/accents';
import { FinanceBalance } from './FinanceBalance';

export function FinancePage() {
  return (
    <PageShell title="Finance">
      <FinanceBalance />
      <Panel accent={accentVarForFeature('finance')}>
        <EmptyState icon="coin" title="Coming Soon" message="Review club budgets, income, and spending." />
      </Panel>
    </PageShell>
  );
}
