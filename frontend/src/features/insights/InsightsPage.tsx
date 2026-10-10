import { useState, type FormEvent } from 'react';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { Money } from '../../components/Money/Money';
import { StatusBadge } from '../../components/StatusBadge/StatusBadge';
import { TextInput } from '../../components/FormField/TextInput';
import { SelectInput } from '../../components/FormField/SelectInput';
import type { ApiError } from '../../api/client';
import { useAuth } from '../../core/hooks/useAuth';
import { useAsync } from '../../core/hooks/useAsync';
import { accentVarForFeature } from '../../core/config/accents';
import { eventsApi } from '../events/api';
import { insightsApi } from './api';
import type { ClubHealth, SaveFile, SimulatorResult } from './types';
import styles from './InsightsPage.module.scss';

export function InsightsPage() {
  const { hasRole } = useAuth();
  const canSimulate = hasRole('event_manager', 'treasurer', 'president');
  const canSeeHealth = hasRole('president');
  const canUseSaveFiles = hasRole('event_manager', 'president');

  if (!canSimulate && !canSeeHealth && !canUseSaveFiles) {
    return (
      <PageShell title="Insights">
        <Panel>
          <p>Your role doesn't have any Insights tools.</p>
        </Panel>
      </PageShell>
    );
  }

  return (
    <PageShell title="Insights">
      {canSimulate && (
        <div className={styles.section}>
          <h2 className={styles.sectionTitle}>Break-even Bench</h2>
          <BreakEvenBench />
        </div>
      )}
      {canSeeHealth && (
        <div className={styles.section}>
          <h2 className={styles.sectionTitle}>Club Health</h2>
          <ClubHealthSection />
        </div>
      )}
      {canUseSaveFiles && (
        <div className={styles.section}>
          <h2 className={styles.sectionTitle}>Save Files</h2>
          <SaveFilesSection />
        </div>
      )}
    </PageShell>
  );
}

function BreakEvenBench() {
  const events = useAsync(() => eventsApi.list(1), []);
  const [ticketPrice, setTicketPrice] = useState('');
  const [attendance, setAttendance] = useState('');
  const [fixedCosts, setFixedCosts] = useState('');
  const [variableCost, setVariableCost] = useState('');
  const [eventId, setEventId] = useState('');
  const [result, setResult] = useState<SimulatorResult | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setFieldErrors({});
    setGeneralError(null);
    setSubmitting(true);
    try {
      const r = await insightsApi.simulate({
        ticketPrice: Math.round(Number(ticketPrice) * 100),
        expectedAttendance: Number(attendance),
        fixedCosts: Math.round(Number(fixedCosts) * 100),
        variableCostPerHead: Math.round(Number(variableCost) * 100),
        ...(eventId ? { event: Number(eventId) } : {}),
      });
      setResult(r);
    } catch (err) {
      const apiErr = err as ApiError;
      if (apiErr.field) setFieldErrors({ [apiErr.field]: apiErr.message });
      else setGeneralError(apiErr.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Panel accent={accentVarForFeature('insights')}>
      {generalError && <ErrorBox error={generalError} />}
      <form onSubmit={submit} noValidate>
        <div className={styles.formRow}>
          <TextInput label="Ticket Price (₹)" type="number" min={0} step="0.01" required value={ticketPrice} onChange={(e) => setTicketPrice(e.target.value)} error={fieldErrors.ticket_price} />
          <TextInput label="Expected Attendance" type="number" min={0} required value={attendance} onChange={(e) => setAttendance(e.target.value)} error={fieldErrors.expected_attendance} />
          <TextInput label="Fixed Costs (₹)" type="number" min={0} step="0.01" required value={fixedCosts} onChange={(e) => setFixedCosts(e.target.value)} error={fieldErrors.fixed_costs} />
          <TextInput
            label="Variable Cost / Head (₹)"
            type="number"
            min={0}
            step="0.01"
            required
            value={variableCost}
            onChange={(e) => setVariableCost(e.target.value)}
            error={fieldErrors.variable_cost_per_head}
          />
        </div>
        <SelectInput
          label="Event (optional — adds forecast vs. actual if it's over)"
          className={styles.eventPicker}
          value={eventId}
          onChange={(e) => setEventId(e.target.value)}
          options={[{ value: '', label: 'None' }, ...(events.data?.results.map((ev) => ({ value: String(ev.id), label: ev.title })) ?? [])]}
        />
        <button type="submit" className={styles.button} disabled={submitting}>
          {submitting ? <Spinner size={16} label="Calculating" /> : 'Calculate'}
        </button>
      </form>

      {result && (
        <>
          <div className={styles.statGrid}>
            <div className={styles.stat}>
              <span className={styles.statLabel}>Break-even Attendance</span>
              <span className={styles.statValue}>{result.breakEvenAttendance}</span>
            </div>
            <div className={styles.stat}>
              <span className={styles.statLabel}>Revenue</span>
              <span className={styles.statValue}>
                <Money paise={result.revenue} />
              </span>
            </div>
            <div className={styles.stat}>
              <span className={styles.statLabel}>Costs</span>
              <span className={styles.statValue}>
                <Money paise={result.costs} />
              </span>
            </div>
            <div className={styles.stat}>
              <span className={styles.statLabel}>Profit</span>
              <span className={`${styles.statValue} ${result.profit >= 0 ? styles.positive : styles.negative}`}>
                <Money paise={result.profit} />
              </span>
            </div>
          </div>
          <StatusBadge variant={result.breaksEven ? 'success' : 'warning'}>{result.breaksEven ? 'Breaks even at this attendance' : 'Does not break even at this attendance'}</StatusBadge>

          {result.forecastVsActual && (
            <table className={styles.forecastTable}>
              <thead>
                <tr>
                  <th></th>
                  <th>Attendance</th>
                  <th>Revenue</th>
                  <th>Costs</th>
                  <th>Profit</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Forecast</td>
                  <td>{result.forecastVsActual.forecast.attendance}</td>
                  <td>
                    <Money paise={result.forecastVsActual.forecast.revenue} />
                  </td>
                  <td>
                    <Money paise={result.forecastVsActual.forecast.costs} />
                  </td>
                  <td>
                    <Money paise={result.forecastVsActual.forecast.profit} />
                  </td>
                </tr>
                <tr>
                  <td>Actual ({result.forecastVsActual.actual.ticketsSold} sold)</td>
                  <td>{result.forecastVsActual.actual.attendance}</td>
                  <td>
                    <Money paise={result.forecastVsActual.actual.revenue} />
                  </td>
                  <td>
                    <Money paise={result.forecastVsActual.actual.costs} />
                  </td>
                  <td>
                    <Money paise={result.forecastVsActual.actual.profit} />
                  </td>
                </tr>
                <tr>
                  <td>Difference</td>
                  <td>{result.forecastVsActual.difference.attendance}</td>
                  <td>
                    <Money paise={result.forecastVsActual.difference.revenue} />
                  </td>
                  <td>
                    <Money paise={result.forecastVsActual.difference.costs} />
                  </td>
                  <td>
                    <Money paise={result.forecastVsActual.difference.profit} />
                  </td>
                </tr>
              </tbody>
            </table>
          )}
        </>
      )}
    </Panel>
  );
}

function ClubHealthSection() {
  const { status, data, error, reload } = useAsync(() => insightsApi.health(), []);

  if (status === 'loading') return <Spinner label="Loading Club Health…" />;
  if (status === 'error') return <ErrorBox error={error!} onRetry={reload} />;
  if (!data) return null;

  return <ClubHealthView health={data} />;
}

function ClubHealthView({ health }: { health: ClubHealth }) {
  return (
    <Panel accent={accentVarForFeature('insights')}>
      <p className={styles.healthScore}>{health.score === null ? '—' : health.score}</p>
      {health.components.map((c) => (
        <Panel key={c.key} className={styles.componentCard}>
          <div className={styles.componentHeader}>
            <span className={styles.componentLabel}>{c.label}</span>
            <span className={styles.componentScore}>
              {c.score === null ? '—' : `${c.score}`} <span className={styles.componentWeight}>(weight {c.weight})</span>
            </span>
          </div>
          <p className={styles.componentReason}>{c.reason}</p>
        </Panel>
      ))}
    </Panel>
  );
}

function SaveFilesSection() {
  const events = useAsync(() => eventsApi.list(1), []);
  const [eventId, setEventId] = useState('');
  const existing = useAsync(() => insightsApi.listSaveFiles(Number(eventId)), [eventId], { enabled: eventId !== '' });

  const [vendors, setVendors] = useState('');
  const [budgetNotes, setBudgetNotes] = useState('');
  const [whatWorked, setWhatWorked] = useState('');
  const [whatDidnt, setWhatDidnt] = useState('');
  const [checklist, setChecklist] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [savedOnce, setSavedOnce] = useState(false);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [loadedFor, setLoadedFor] = useState<string | null>(null);

  const current: SaveFile | undefined = existing.data?.results[0];
  if (existing.status === 'success' && loadedFor !== eventId) {
    setLoadedFor(eventId);
    setVendors(current?.vendors ?? '');
    setBudgetNotes(current?.budgetNotes ?? '');
    setWhatWorked(current?.whatWorked ?? '');
    setWhatDidnt(current?.whatDidnt ?? '');
    setChecklist(current?.checklist ?? []);
    setSavedOnce(false);
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setGeneralError(null);
    setSaving(true);
    try {
      await insightsApi.saveSaveFile({ event: Number(eventId), vendors, budgetNotes, whatWorked, whatDidnt, checklist: checklist.filter((c) => c.trim()) });
      setSavedOnce(true);
      existing.reload();
    } catch (err) {
      setGeneralError((err as ApiError).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Panel accent={accentVarForFeature('insights')}>
      <SelectInput
        label="Event"
        className={styles.eventPicker}
        value={eventId}
        onChange={(e) => setEventId(e.target.value)}
        options={[{ value: '', label: 'Choose an event…' }, ...(events.data?.results.map((ev) => ({ value: String(ev.id), label: ev.title })) ?? [])]}
      />

      {eventId && existing.status === 'loading' && <Spinner label="Loading…" />}
      {eventId && existing.status === 'error' && <ErrorBox error={existing.error!} onRetry={existing.reload} />}
      {eventId && existing.status === 'success' && (
        <form onSubmit={submit} noValidate>
          {generalError && <ErrorBox error={generalError} />}
          {savedOnce && <p className={styles.successNote}>Saved.</p>}
          <div className={styles.saveFileGrid}>
            <div>
              <label className={styles.fieldLabel} htmlFor="sf-vendors">
                Vendors
              </label>
              <textarea id="sf-vendors" className={styles.textarea} value={vendors} onChange={(e) => setVendors(e.target.value)} />
            </div>
            <div>
              <label className={styles.fieldLabel} htmlFor="sf-budget">
                Budget Notes
              </label>
              <textarea id="sf-budget" className={styles.textarea} value={budgetNotes} onChange={(e) => setBudgetNotes(e.target.value)} />
            </div>
            <div>
              <label className={styles.fieldLabel} htmlFor="sf-worked">
                What Worked
              </label>
              <textarea id="sf-worked" className={styles.textarea} value={whatWorked} onChange={(e) => setWhatWorked(e.target.value)} />
            </div>
            <div>
              <label className={styles.fieldLabel} htmlFor="sf-didnt">
                What Didn't
              </label>
              <textarea id="sf-didnt" className={styles.textarea} value={whatDidnt} onChange={(e) => setWhatDidnt(e.target.value)} />
            </div>
          </div>

          <label className={styles.fieldLabel}>Checklist</label>
          {checklist.map((item, i) => (
            <div key={i} className={styles.checklistRow}>
              <input
                className={styles.checklistInput}
                value={item}
                onChange={(e) =>
                  setChecklist((list) => {
                    const next = [...list];
                    next[i] = e.target.value;
                    return next;
                  })
                }
              />
              <button type="button" className={styles.removeButton} onClick={() => setChecklist((list) => list.filter((_, idx) => idx !== i))} aria-label="Remove item">
                ×
              </button>
            </div>
          ))}
          <button type="button" className={styles.addButton} onClick={() => setChecklist((list) => [...list, ''])}>
            + Add checklist item
          </button>

          <div>
            <button type="submit" className={styles.button} disabled={saving}>
              {saving ? <Spinner size={16} label="Saving" /> : 'Save'}
            </button>
          </div>
        </form>
      )}
    </Panel>
  );
}
