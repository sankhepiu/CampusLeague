import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { Money } from '../../components/Money/Money';
import { useAsync } from '../../core/hooks/useAsync';
import { financeApi } from './api';
import type { TraceEntry, TraceSource } from './types';
import styles from './CoinTrail.module.scss';

interface CoinTrailProps {
  /** The figure to trace, or null when the panel should be closed. */
  figure: string | null;
  onClose: () => void;
}

/** Side panel (>=1024px) / full-screen (phones) drilldown from a summary
 * figure, through its ledger entries, down to the record behind one entry.
 * Breadcrumb: Summary > Figure > Entry > Source. */
export function CoinTrail({ figure, onClose }: CoinTrailProps) {
  const [selectedEntry, setSelectedEntry] = useState<TraceEntry | null>(null);
  const { status, data, error, reload } = useAsync(() => financeApi.trace(figure!), [figure], { enabled: figure !== null });

  // Reset the drilldown level whenever a new figure is opened.
  useEffect(() => {
    setSelectedEntry(null);
  }, [figure]);

  if (figure === null) return null;

  // Portalled to document.body: FinancePage/LedgerPage render this inside
  // the routed <Outlet>, whose RouteTransition wrapper animates opacity —
  // that creates a stacking context which traps any z-index here below the
  // app TopBar no matter how high it's set. Escaping via portal, the same
  // way every other overlay (Toast, ConfirmDialog, Fanfare) avoids it by
  // mounting above the router outlet instead.
  return createPortal(
    <>
      <div className={styles.backdrop} onClick={onClose} />
      <div className={styles.panel} role="dialog" aria-modal="true" aria-label="Coin Trail">
        <div className={styles.header}>
          <nav className={styles.breadcrumb} aria-label="Breadcrumb">
            <button type="button" className={styles.crumbButton} onClick={onClose}>
              Summary
            </button>
            {status === 'success' && (
              <>
                <span className={styles.crumbSep}>&gt;</span>
                {selectedEntry ? (
                  <button type="button" className={styles.crumbButton} onClick={() => setSelectedEntry(null)}>
                    {data.label}
                  </button>
                ) : (
                  <span className={styles.crumbCurrent}>{data.label}</span>
                )}
              </>
            )}
            {selectedEntry && (
              <>
                <span className={styles.crumbSep}>&gt;</span>
                <span className={styles.crumbCurrent}>Entry</span>
                <span className={styles.crumbSep}>&gt;</span>
                <span className={styles.crumbCurrent}>Source</span>
              </>
            )}
          </nav>
          <button type="button" className={styles.closeButton} onClick={onClose} aria-label="Close Coin Trail">
            X
          </button>
        </div>

        <div className={styles.body}>
          {status === 'loading' && <Spinner label="Loading…" />}
          {status === 'error' && <ErrorBox error={error!} onRetry={reload} />}
          {status === 'success' && !selectedEntry && (
            <FigureView label={data.label} total={data.total} entryCount={data.entryCount} entries={data.entries} onSelect={setSelectedEntry} />
          )}
          {status === 'success' && selectedEntry && <EntryView entry={selectedEntry} />}
        </div>
      </div>
    </>,
    document.body,
  );
}

function FigureView({
  label,
  total,
  entryCount,
  entries,
  onSelect,
}: {
  label: string;
  total: number;
  entryCount: number;
  entries: TraceEntry[];
  onSelect: (entry: TraceEntry) => void;
}) {
  return (
    <>
      <h2 className={styles.figureTitle}>{label}</h2>
      <p className={`${styles.figureTotal} ${total >= 0 ? styles.positive : styles.negative}`}>
        <Money paise={total} />
      </p>
      {entryCount > entries.length && <p className={styles.cappedNote}>Showing latest {entries.length} of {entryCount}</p>}
      {entries.length === 0 && <p className={styles.cappedNote}>No entries.</p>}
      <div className={styles.entryList}>
        {entries.map((entry) => (
          <button key={entry.id} type="button" className={styles.entryRow} onClick={() => onSelect(entry)}>
            <span className={styles.entryMeta}>
              <span className={styles.entryDescription}>{entry.description}</span>
              <span className={styles.entryDate}>{new Date(entry.postedAt).toLocaleString('en-IN')}</span>
            </span>
            <span className={`${styles.entryAmount} ${entry.amount >= 0 ? styles.positive : styles.negative}`}>
              <Money paise={entry.amount} />
            </span>
          </button>
        ))}
      </div>
    </>
  );
}

function EntryView({ entry }: { entry: TraceEntry }) {
  return (
    <>
      <h2 className={styles.figureTitle}>{entry.description}</h2>
      <p className={styles.entryDate}>{new Date(entry.postedAt).toLocaleString('en-IN')}</p>

      <table className={styles.linesTable}>
        <thead>
          <tr>
            <th>Account</th>
            <th>Debit</th>
            <th>Credit</th>
          </tr>
        </thead>
        <tbody>
          {entry.lines.map((line) => (
            <tr key={line.id}>
              <td>
                {line.account.code} {line.account.name}
              </td>
              <td>{line.debit > 0 ? <Money paise={line.debit} /> : '—'}</td>
              <td>{line.credit > 0 ? <Money paise={line.credit} /> : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <SourceView source={entry.source} />
    </>
  );
}

function SourceView({ source }: { source: TraceSource }) {
  return (
    <div className={styles.sourceSection}>
      <p className={styles.sourceLabel}>Source — {source.label}</p>
      {source.type === 'order_line' && (
        <table className={styles.ticketTable}>
          <thead>
            <tr>
              <th>Code</th>
              <th>Holder</th>
              <th>Price</th>
              <th>Status</th>
              <th>Checked In</th>
            </tr>
          </thead>
          <tbody>
            {source.details.tickets.map((t) => (
              <tr key={t.id}>
                <td>{t.code}</td>
                <td>{t.holder}</td>
                <td>
                  <Money paise={t.pricePaid} />
                </td>
                <td>{t.status}</td>
                <td>{t.checkedInAt ? new Date(t.checkedInAt).toLocaleString('en-IN') : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {source.type === 'order' && (
        <table className={styles.ticketTable}>
          <thead>
            <tr>
              <th>Product</th>
              <th>Size</th>
              <th>Qty</th>
              <th>Unit Price</th>
            </tr>
          </thead>
          <tbody>
            {source.details.items.map((item, i) => (
              <tr key={i}>
                <td>{item.product}</td>
                <td>{item.size}</td>
                <td>{item.qty}</td>
                <td>
                  <Money paise={item.unitPrice} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {source.type === 'payment' && (
        <>
          <div className={styles.kv}>
            <span>Payer</span>
            <span>{source.details.payer}</span>
          </div>
          <div className={styles.kv}>
            <span>Plan</span>
            <span>{source.details.plan}</span>
          </div>
        </>
      )}

      {source.type === 'expense_request' && (
        <>
          <div className={styles.kv}>
            <span>Requester</span>
            <span>{source.details.requester}</span>
          </div>
          <div className={styles.kv}>
            <span>Description</span>
            <span>{source.details.description}</span>
          </div>
          {source.details.approvedBy && (
            <div className={styles.kv}>
              <span>Approved By</span>
              <span>{source.details.approvedBy}</span>
            </div>
          )}
          {source.details.receiptUrl && (
            <a href={source.details.receiptUrl} target="_blank" rel="noreferrer" className={styles.receiptLink}>
              View Receipt
            </a>
          )}
        </>
      )}

      {source.type === 'fundraiser_sale' && (
        <>
          <div className={styles.kv}>
            <span>Fundraiser</span>
            <span>{source.details.fundraiser}</span>
          </div>
          {source.details.note && (
            <div className={styles.kv}>
              <span>Note</span>
              <span>{source.details.note}</span>
            </div>
          )}
        </>
      )}
    </div>
  );
}
