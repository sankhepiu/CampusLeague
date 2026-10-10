import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { TextInput } from '../../components/FormField/TextInput';
import { SelectInput } from '../../components/FormField/SelectInput';
import { Spinner } from '../../components/Spinner/Spinner';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { useAsync } from '../../core/hooks/useAsync';
import { eventsApi } from '../events/api';
import { checkinApi } from './api';
import type { CheckinResponse } from './types';
import { useQrScanner } from './useQrScanner';
import styles from './CheckinPage.module.scss';

const DOUBLE_SCAN_WINDOW_MS = 2000;

export function CheckinPage() {
  const eventsState = useAsync(() => eventsApi.list(1), []);
  const [selectedEvent, setSelectedEvent] = useState<string>('');

  const [manualCode, setManualCode] = useState('');
  const [result, setResult] = useState<CheckinResponse | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const lastScan = useRef<{ value: string; at: number } | null>(null);
  const resultRef = useRef<CheckinResponse | null>(null);
  useEffect(() => {
    resultRef.current = result;
  }, [result]);
  const submittingRef = useRef(false);

  const submitScan = useCallback(
    async (params: { token?: string; code?: string }) => {
      if (submittingRef.current || resultRef.current) return;
      submittingRef.current = true;
      setSubmitting(true);
      setSubmitError(null);
      try {
        const eventId = selectedEvent ? Number(selectedEvent) : undefined;
        const response = await checkinApi.scan({ ...params, event: eventId });
        setResult(response);
      } catch (err) {
        setSubmitError((err as { message?: string }).message ?? 'Could not reach the check-in service.');
      } finally {
        submittingRef.current = false;
        setSubmitting(false);
      }
    },
    [selectedEvent],
  );

  const onDecode = useCallback(
    (text: string) => {
      const now = Date.now();
      if (lastScan.current && lastScan.current.value === text && now - lastScan.current.at < DOUBLE_SCAN_WINDOW_MS) return;
      lastScan.current = { value: text, at: now };
      void submitScan({ token: text });
    },
    [submitScan],
  );

  const { videoRef, cameraState } = useQrScanner(onDecode, !result);

  const onManualSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!manualCode.trim()) return;
    void submitScan({ code: manualCode.trim() });
    setManualCode('');
  };

  const scanNext = () => {
    setResult(null);
    setSubmitError(null);
  };

  useEffect(() => {
    if (!result) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') scanNext();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [result]);

  return (
    <PageShell title="Check-in Scanner">
      <div className={styles.eventPicker}>
        {eventsState.status === 'success' && (
          <SelectInput
            label="Event"
            hint="Optional — leave on Any event to accept tickets from any event."
            value={selectedEvent}
            onChange={(e) => setSelectedEvent(e.target.value)}
            options={[{ value: '', label: 'Any event' }, ...eventsState.data.results.map((ev) => ({ value: String(ev.id), label: ev.title }))]}
          />
        )}
      </div>

      <div className={styles.layout}>
        <Panel>
          <div className={styles.cameraBox}>
            {cameraState === 'denied' || cameraState === 'unavailable' ? (
              <p className={styles.cameraFallback}>
                {cameraState === 'denied' ? 'Camera access was denied.' : 'No camera available.'} Use the code field below instead.
              </p>
            ) : (
              // eslint-disable-next-line jsx-a11y/media-has-caption
              <video ref={videoRef} className={styles.video} muted playsInline />
            )}
          </div>
        </Panel>

        <Panel>
          {submitError && <ErrorBox error={submitError} onRetry={() => setSubmitError(null)} />}
          <form onSubmit={onManualSubmit} className={styles.manualForm}>
            <TextInput
              label="Manual code entry"
              placeholder="e.g. K7MPQ2XD"
              value={manualCode}
              onChange={(e) => setManualCode(e.target.value)}
              autoFocus
            />
            <button type="submit" className={styles.submitButton} disabled={submitting || !manualCode.trim()}>
              {submitting ? <Spinner size={16} label="Checking" /> : 'Check In'}
            </button>
          </form>
        </Panel>
      </div>

      {result && <ResultOverlay result={result} onScanNext={scanNext} />}
    </PageShell>
  );
}

function ResultOverlay({ result, onScanNext }: { result: CheckinResponse; onScanNext: () => void }) {
  const variantClass =
    result.result === 'ok' ? styles.resultOk : result.result === 'already_checked_in' || result.result === 'cancelled' || result.result === 'invalid' ? styles.resultDanger : styles.resultDanger;

  const title =
    result.result === 'ok'
      ? 'Checked In'
      : result.result === 'already_checked_in'
        ? 'Already Checked In'
        : result.result === 'cancelled'
          ? 'Ticket Cancelled'
          : 'Invalid Ticket or Wrong Event';

  const icon = result.result === 'ok' ? '✓' : result.result === 'already_checked_in' ? '⟳' : '✕';
  const isActiveMember = result.membershipStatus === 'active';

  return (
    <div className={`${styles.resultOverlay} ${variantClass}`} role="status" aria-live="assertive">
      <div>
        <div className={styles.resultIcon}>{icon}</div>
        <h2 className={styles.resultTitle}>{title}</h2>

        {result.holderName && <p className={styles.resultDetail}>{result.holderName}</p>}
        {result.ticket && <p className={styles.resultDetail}>{result.ticket.tier.name}</p>}

        {result.membershipStatus !== null && (
          <p className={result.result === 'ok' ? `${styles.resultSub} ${isActiveMember ? styles.resultOk : styles.resultWarn}` : styles.resultSub}>
            {isActiveMember ? 'Active member' : 'Not a member'}
          </p>
        )}

        {result.result === 'already_checked_in' && (
          <>
            <p className={styles.resultSub}>Originally checked in: {result.checkedInAt ? new Date(result.checkedInAt).toLocaleString('en-IN') : '—'}</p>
            <p className={styles.resultSub}>By: {result.checkedInBy ?? '—'}</p>
          </>
        )}

        <button type="button" className={styles.scanNextButton} onClick={onScanNext} autoFocus>
          Scan Next
        </button>
      </div>
    </div>
  );
}
