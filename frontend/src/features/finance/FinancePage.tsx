import { useState } from 'react';
import { Link } from 'react-router-dom';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { Money } from '../../components/Money/Money';
import { PnlCard } from '../../components/PnlCard/PnlCard';
import { SelectInput } from '../../components/FormField/SelectInput';
import { useAsync } from '../../core/hooks/useAsync';
import { accentVarForFeature } from '../../core/config/accents';
import { eventsApi } from '../events/api';
import { financeApi } from './api';
import { CoinTrail } from './CoinTrail';
import { ReconcileBadge } from './ReconcileBadge';
import type { FinanceSummary } from './types';
import styles from './FinancePage.module.scss';

export function FinancePage() {
  const { status, data, error, reload } = useAsync(() => financeApi.summary(), []);
  const [trailFigure, setTrailFigure] = useState<string | null>(null);
  const [eventId, setEventId] = useState('');

  const events = useAsync(() => eventsApi.list(1), []);
  const pnl = useAsync(() => eventsApi.pnl(Number(eventId)), [eventId], { enabled: eventId !== '' });

  return (
    <PageShell title="Finance">
      <ReconcileBadge />

      {status === 'loading' && <Spinner fullPage label="Loading finance summary…" />}
      {status === 'error' && <ErrorBox error={error!} onRetry={reload} />}
      {status === 'success' && <SummaryStats summary={data} onOpenTrail={setTrailFigure} />}

      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>By Event</h2>
        </div>
        <SelectInput
          label="Event"
          className={styles.eventPicker}
          value={eventId}
          onChange={(e) => setEventId(e.target.value)}
          options={[{ value: '', label: 'Choose an event…' }, ...(events.data?.results.map((ev) => ({ value: String(ev.id), label: ev.title })) ?? [])]}
        />
        {pnl.status === 'loading' && <Spinner label="Loading P&L…" />}
        {pnl.status === 'error' && <ErrorBox error={pnl.error!} onRetry={pnl.reload} />}
        {pnl.status === 'success' && (
          <PnlCard title={`${pnl.data.event.title}: Profit & Loss`} data={pnl.data} accent={accentVarForFeature('finance')} onProfitClick={() => setTrailFigure(`event:${eventId}:profit`)} />
        )}
      </div>

      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>Ledger</h2>
          <Link to="/finance/ledger" className={styles.ledgerLink}>
            View Full Ledger
          </Link>
        </div>
      </div>

      <CoinTrail figure={trailFigure} onClose={() => setTrailFigure(null)} />
    </PageShell>
  );
}

function SummaryStats({ summary, onOpenTrail }: { summary: FinanceSummary; onOpenTrail: (figure: string) => void }) {
  return (
    <div className={styles.readable}>
      <div className={styles.statGrid}>
        <Panel accent="var(--cl-green)" className={styles.statCard}>
          <span className={styles.statLabel}>Came In</span>
          <button type="button" className={`${styles.statButton} ${styles.statValue} ${styles.positive}`} onClick={() => onOpenTrail('came_in')}>
            <Money paise={summary.cameIn.total} />
          </button>
        </Panel>
        <Panel accent="var(--cl-coral)" className={styles.statCard}>
          <span className={styles.statLabel}>Went Out</span>
          <button type="button" className={`${styles.statButton} ${styles.statValue} ${styles.negative}`} onClick={() => onOpenTrail('went_out')}>
            <Money paise={summary.wentOut.total} />
          </button>
        </Panel>
        <Panel accent={accentVarForFeature('finance')} className={styles.statCard}>
          <span className={styles.statLabel}>Net</span>
          <span className={`${styles.statValue} ${summary.net >= 0 ? styles.positive : styles.negative}`}>
            <Money paise={summary.net} />
          </span>
        </Panel>
        <Panel accent={accentVarForFeature('finance')} className={styles.statCard}>
          <span className={styles.statLabel}>Cash</span>
          <button type="button" className={`${styles.statButton} ${styles.statValue}`} onClick={() => onOpenTrail('cash')}>
            <Money paise={summary.cash} />
          </button>
        </Panel>
        <Panel accent="var(--cl-coral)" className={styles.statCard}>
          <span className={styles.statLabel}>Payable</span>
          <button type="button" className={`${styles.statButton} ${styles.statValue}`} onClick={() => onOpenTrail('payable')}>
            <Money paise={summary.payable} />
          </button>
        </Panel>
      </div>
      <p className={styles.netNote}>Net differs from cash by exactly payable — approved reimbursements not yet paid out.</p>

      <div className={styles.breakdownGrid}>
        <Panel accent="var(--cl-green)">
          <h3 className={styles.breakdownTitle}>Came In by account</h3>
          <ul className={styles.breakdownRows}>
            {summary.cameIn.byAccount.map((line) => (
              <li key={line.code}>
                <button type="button" className={styles.breakdownRow} onClick={() => onOpenTrail(`account:${line.code}`)}>
                  <span>{line.name}</span>
                  <span className={styles.positive}>
                    <Money paise={line.amount} />
                  </span>
                </button>
              </li>
            ))}
            {summary.cameIn.byAccount.length === 0 && <li className={styles.breakdownRow}>No revenue yet.</li>}
          </ul>
        </Panel>
        <Panel accent="var(--cl-coral)">
          <h3 className={styles.breakdownTitle}>Went Out by account</h3>
          <ul className={styles.breakdownRows}>
            {summary.wentOut.byAccount.map((line) => (
              <li key={line.code}>
                <button type="button" className={styles.breakdownRow} onClick={() => onOpenTrail(`account:${line.code}`)}>
                  <span>{line.name}</span>
                  <span className={styles.negative}>
                    <Money paise={line.amount} />
                  </span>
                </button>
              </li>
            ))}
            {summary.wentOut.byAccount.length === 0 && <li className={styles.breakdownRow}>No expenses yet.</li>}
          </ul>
        </Panel>
      </div>
    </div>
  );
}
