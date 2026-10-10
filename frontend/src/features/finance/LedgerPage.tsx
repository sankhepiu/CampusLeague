import { useState } from 'react';
import { PageShell } from '../../components/PageShell/PageShell';
import { DataTable, type DataTableColumn } from '../../components/DataTable/DataTable';
import { SelectInput } from '../../components/FormField/SelectInput';
import { Money } from '../../components/Money/Money';
import { useAsync } from '../../core/hooks/useAsync';
import { eventsApi } from '../events/api';
import { financeApi } from './api';
import { ACCOUNT_LIST } from './accountCodes';
import { CoinTrail } from './CoinTrail';
import type { LedgerEntry, LedgerKind } from './types';
import styles from './LedgerPage.module.scss';
import { formatDateOnly } from '../../core/utils/formatDateTime';

const KIND_OPTIONS: { value: LedgerKind | ''; label: string }[] = [
  { value: '', label: 'All kinds' },
  { value: 'membership_dues', label: 'Membership dues' },
  { value: 'ticket_sale', label: 'Ticket sale' },
  { value: 'merch_sale', label: 'Merch sale' },
  { value: 'fundraiser_sale', label: 'Fundraiser sale' },
  { value: 'expense_approved', label: 'Expense approved' },
  { value: 'expense_paid', label: 'Expense paid' },
];

const REVENUE_ACCOUNT_BY_KIND: Partial<Record<LedgerKind, string>> = {
  membership_dues: '4000',
  ticket_sale: '4100',
  merch_sale: '4200',
  fundraiser_sale: '4300',
};

/** Best-effort figure to open in the Coin Trail for a ledger row — there's
 * no "fetch one entry" endpoint, only trace-by-figure, so this opens the
 * narrowest figure that is guaranteed to contain the entry. */
function figureForEntry(entry: LedgerEntry): string {
  if (entry.event !== null) {
    if (entry.kind === 'ticket_sale') return `event:${entry.event}:revenue`;
    if (entry.kind === 'expense_approved' || entry.kind === 'expense_paid') return `event:${entry.event}:expenses`;
  }
  const account = REVENUE_ACCOUNT_BY_KIND[entry.kind];
  if (account) return `account:${account}`;
  if (entry.kind === 'expense_approved') return 'went_out';
  return 'cash';
}

export function LedgerPage() {
  const [account, setAccount] = useState('');
  const [eventId, setEventId] = useState('');
  const [kind, setKind] = useState<LedgerKind | ''>('');
  const [page, setPage] = useState(1);
  const [trailFigure, setTrailFigure] = useState<string | null>(null);

  const events = useAsync(() => eventsApi.list(1), []);
  const { status, data, error, reload } = useAsync(
    () => financeApi.ledger({ account: account || undefined, event: eventId ? Number(eventId) : undefined, kind: kind || undefined }, page),
    [account, eventId, kind, page],
  );

  const columns: DataTableColumn<LedgerEntry>[] = [
    { key: 'date', header: 'Date', render: (e) => formatDateOnly(e.postedAt) },
    { key: 'description', header: 'Description', wrap: true, render: (e) => e.description },
    { key: 'kind', header: 'Kind', render: (e) => e.kind.replace(/_/g, ' ') },
    { key: 'event', header: 'Event', render: (e) => (e.event !== null ? `#${e.event}` : '—') },
    {
      key: 'account',
      header: 'Account',
      render: (e) => (
        <div className={styles.lineStack}>
          {e.lines.map((line) => (
            <div key={line.id}>
              {line.account.code} {line.account.name}
            </div>
          ))}
        </div>
      ),
    },
    {
      key: 'debit',
      header: 'Debit',
      align: 'right',
      render: (e) => (
        <div className={styles.lineStack}>
          {e.lines.map((line) => (
            <div key={line.id}>{line.debit > 0 ? <Money paise={line.debit} /> : '—'}</div>
          ))}
        </div>
      ),
    },
    {
      key: 'credit',
      header: 'Credit',
      align: 'right',
      render: (e) => (
        <div className={styles.lineStack}>
          {e.lines.map((line) => (
            <div key={line.id}>{line.credit > 0 ? <Money paise={line.credit} /> : '—'}</div>
          ))}
        </div>
      ),
    },
    {
      key: 'trail',
      header: '',
      render: (e) => (
        <button type="button" className={styles.viewButton} onClick={() => setTrailFigure(figureForEntry(e))}>
          View
        </button>
      ),
    },
  ];

  return (
    <PageShell title="Ledger">
      <div className={styles.filterRow}>
        <SelectInput
          label="Account"
          value={account}
          onChange={(e) => {
            setAccount(e.target.value);
            setPage(1);
          }}
          options={[{ value: '', label: 'All accounts' }, ...ACCOUNT_LIST.map((a) => ({ value: a.code, label: `${a.code} ${a.name}` }))]}
        />
        <SelectInput
          label="Event"
          value={eventId}
          onChange={(e) => {
            setEventId(e.target.value);
            setPage(1);
          }}
          options={[{ value: '', label: 'All events' }, ...(events.data?.results.map((ev) => ({ value: String(ev.id), label: ev.title })) ?? [])]}
        />
        <SelectInput
          label="Kind"
          value={kind}
          onChange={(e) => {
            setKind(e.target.value as LedgerKind | '');
            setPage(1);
          }}
          options={KIND_OPTIONS}
        />
      </div>

      <div className={styles.readable}>
        <DataTable
          columns={columns}
          rows={data?.results ?? []}
          rowKey={(e) => String(e.id)}
          isLoading={status === 'loading'}
          error={status === 'error' ? error : null}
          onRetry={reload}
          emptyMessage="No ledger entries match these filters."
        />
      </div>

      {status === 'success' && (
        <div className={styles.pagination}>
          <button type="button" className={styles.pageButton} onClick={() => setPage((p) => p - 1)} disabled={!data.previous}>
            ← Previous
          </button>
          <button type="button" className={styles.pageButton} onClick={() => setPage((p) => p + 1)} disabled={!data.next}>
            Next →
          </button>
        </div>
      )}

      <CoinTrail figure={trailFigure} onClose={() => setTrailFigure(null)} />
    </PageShell>
  );
}
