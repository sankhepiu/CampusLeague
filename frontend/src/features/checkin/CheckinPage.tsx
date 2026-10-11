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
import type { MemberScanResponse, ScanOutcome } from './types';
import { formatDateTime } from '../../core/utils/formatDateTime';
import { useQrScanner } from './useQrScanner';
import styles from './CheckinPage.module.scss';

const DOUBLE_SCAN_WINDOW_MS = 2000;

export function CheckinPage() {
  const eventsState = useAsync(() => eventsApi.list(1), []);
  const [selectedEvent, setSelectedEvent] = useState<string>('');

  const [manualCode, setManualCode] = useState('');
  const [result, setResult] = useState<ScanOutcome | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  // Only matters for a group pass — ignored by the server for a ticket or
  // member card. Set once before scanning since we can't know ahead of time
  // which kind of code a camera scan will turn out to be.
  const [admitCount, setAdmitCount] = useState(1);

  const lastScan = useRef<{ value: string; at: number } | null>(null);
  const resultRef = useRef<ScanOutcome | null>(null);
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
        const outcome = await checkinApi.scan({ ...params, count: admitCount, event: eventId });
        // A scanned QR is a ticket, a group pass, or a member card, and
        // they're opaque strings we can't tell apart up front. The server
        // (or mock) already tried pass-then-ticket; only when it comes back
        // as an invalid ticket do we ask whether it's a member card instead.
        // A member-card lookup records nothing, so the extra question is
        // harmless. (Typed codes are always tickets.)
        if (outcome.kind === 'ticket' && outcome.result === 'invalid' && params.token) {
          const member = await checkinApi.scanMember(params.token);
          if (member.result !== 'invalid') {
            setResult({ kind: 'member', ...member });
            return;
          }
        }
        setResult(outcome);
      } catch (err) {
        setSubmitError((err as { message?: string }).message ?? 'Could not reach the check-in service.');
      } finally {
        submittingRef.current = false;
        setSubmitting(false);
      }
    },
    [selectedEvent, admitCount],
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
    const value = manualCode.trim();
    if (!value) return;
    // A typed ticket code is 8 letters and digits. Anything containing ":"
    // is the full signed content of a QR code (a ticket or a member card)
    // that was pasted in, so it goes down the same path as a camera scan.
    void submitScan(value.includes(':') ? { token: value } : { code: value });
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

          <div className={styles.admitCountRow}>
            <span>Admit how many</span>
            <button type="button" className={styles.qtyButton} onClick={() => setAdmitCount((c) => Math.max(1, c - 1))} disabled={admitCount <= 1}>
              −
            </button>
            <span className={styles.admitCountValue}>{admitCount}</span>
            <button type="button" className={styles.qtyButton} onClick={() => setAdmitCount((c) => Math.min(10, c + 1))} disabled={admitCount >= 10}>
              +
            </button>
            <span className={styles.admitCountHint}>Only used for a group pass — ignored for a single ticket.</span>
          </div>

          <form onSubmit={onManualSubmit} className={styles.manualForm}>
            <TextInput
              label="Manual entry"
              hint="Type the 8-character ticket code, or paste the full text of a ticket, pass or member-card QR."
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

const MEMBER_CARD_VIEW: Record<MemberScanResponse['result'], { className: string; icon: string; title: string; note: string }> = {
  // Green: a current member.
  member_ok: { className: styles.resultOk, icon: '✓', title: 'Active Member', note: 'Membership is active today.' },
  // Amber: a genuine card, but the membership is not active.
  not_member: { className: styles.resultWarn, icon: '!', title: 'Not a Current Member', note: 'This card is genuine, but the membership is not active.' },
  // Red: forged, altered, or not a Campus League code at all.
  invalid: { className: styles.resultDanger, icon: '✕', title: 'Invalid Card', note: 'This code is not a valid member card.' },
};

function MemberCardResult({ result, onScanNext }: { result: MemberScanResponse; onScanNext: () => void }) {
  const view = MEMBER_CARD_VIEW[result.result];
  return (
    <div className={`${styles.resultOverlay} ${view.className}`} role="status" aria-live="assertive">
      <div>
        <p className={styles.resultKind}>Member card</p>
        <div className={styles.resultIcon}>{view.icon}</div>
        <h2 className={styles.resultTitle}>{view.title}</h2>

        {result.holder && (
          <>
            <p className={styles.resultDetail}>{result.holder.name}</p>
            <p className={styles.resultSub}>{result.holder.email}</p>
          </>
        )}
        <p className={styles.resultSub}>
          {view.note}
          {result.membershipStatus === 'lapsed' && ' It has lapsed.'}
          {result.membershipStatus === 'none' && ' No membership on record.'}
        </p>
        <p className={styles.resultSub}>No check-in was recorded: a member card is not a ticket.</p>

        <button type="button" className={styles.scanNextButton} onClick={onScanNext} autoFocus>
          Scan Next
        </button>
      </div>
    </div>
  );
}

function PassScanOverlay({ result, onScanNext }: { result: Extract<ScanOutcome, { kind: 'pass' }>; onScanNext: () => void }) {
  const variantClass = result.result === 'admitted' ? styles.resultOk : result.result === 'wrong_event' || result.result === 'invalid' ? styles.resultDanger : styles.resultWarn;
  const title =
    result.result === 'admitted'
      ? 'Admitted'
      : result.result === 'already_used'
        ? 'Pass Already Used'
        : result.result === 'wrong_event'
          ? 'Wrong Event'
          : 'Invalid Pass';
  const icon = result.result === 'admitted' ? '✓' : result.result === 'wrong_event' || result.result === 'invalid' ? '✕' : '⟳';
  const isActiveMember = result.membershipStatus === 'active';

  return (
    <div className={`${styles.resultOverlay} ${variantClass}`} role="status" aria-live="assertive">
      <div>
        <p className={styles.resultKind}>Group pass</p>
        <div className={styles.resultIcon}>{icon}</div>
        <h2 className={styles.resultTitle}>{title}</h2>

        {result.holder && <p className={styles.resultDetail}>{result.holder.name}</p>}
        {result.tier && <p className={styles.resultDetail}>{result.tier.name}</p>}

        {result.total !== null && (
          <p className={styles.resultSub}>
            Admitted {result.admitted} of {result.total} — {result.remaining} remaining
          </p>
        )}
        {result.result === 'admitted' && <p className={styles.resultSub}>{result.admittedNow} admitted on this scan.</p>}

        {result.membershipStatus !== null && (
          <p className={isActiveMember ? `${styles.resultSub} ${styles.resultOk}` : `${styles.resultSub} ${styles.resultWarn}`}>
            {isActiveMember ? 'Active member' : 'Not a member'}
          </p>
        )}

        <button type="button" className={styles.scanNextButton} onClick={onScanNext} autoFocus>
          Scan Next
        </button>
      </div>
    </div>
  );
}

function ResultOverlay({ result, onScanNext }: { result: ScanOutcome; onScanNext: () => void }) {
  if (result.kind === 'member') return <MemberCardResult result={result} onScanNext={onScanNext} />;
  if (result.kind === 'pass') return <PassScanOverlay result={result} onScanNext={onScanNext} />;

  const variantClass = result.result === 'ok' ? styles.resultOk : styles.resultDanger;

  const title =
    result.result === 'ok'
      ? 'Checked In'
      : result.result === 'already_checked_in'
        ? 'Already Checked In'
        : result.result === 'cancelled'
          ? 'Ticket Cancelled'
          : 'Invalid Code or Wrong Event';

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
            <p className={styles.resultSub}>Originally checked in: {result.checkedInAt ? formatDateTime(result.checkedInAt) : '—'}</p>
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
