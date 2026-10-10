import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { TextInput } from '../../components/FormField/TextInput';
import { SelectInput } from '../../components/FormField/SelectInput';
import type { ApiError } from '../../api/client';
import { useAsync } from '../../core/hooks/useAsync';
import { accentVarForFeature } from '../../core/config/accents';
import { volunteeringApi } from './api';
import type { Fundraiser, FundraiserStatus } from './types';
import styles from './FundraiserAdminPage.module.scss';

const STATUS_OPTIONS: { value: FundraiserStatus; label: string }[] = [
  { value: 'planned', label: 'Planned' },
  { value: 'active', label: 'Active' },
  { value: 'closed', label: 'Closed' },
];

interface FormState {
  title: string;
  goalAmount: string;
  startsOn: string;
  endsOn: string;
  status: FundraiserStatus;
}

const EMPTY_FORM: FormState = { title: '', goalAmount: '', startsOn: '', endsOn: '', status: 'planned' };

function toForm(f: Fundraiser): FormState {
  return { title: f.title, goalAmount: (f.goalAmount / 100).toString(), startsOn: f.startsOn, endsOn: f.endsOn, status: f.status };
}

export function FundraiserAdminPage() {
  const { id } = useParams<{ id: string }>();
  const isEdit = id !== undefined;
  const fundraiserId = isEdit ? Number(id) : null;
  const navigate = useNavigate();

  const existing = useAsync(() => volunteeringApi.getFundraiser(fundraiserId!), [fundraiserId], { enabled: isEdit });

  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedOnce, setSavedOnce] = useState(false);

  const [saleAmount, setSaleAmount] = useState('');
  const [saleNote, setSaleNote] = useState('');
  const [recordingSale, setRecordingSale] = useState(false);
  const [saleError, setSaleError] = useState<string | null>(null);
  const [saleNoteSuccess, setSaleNoteSuccess] = useState(false);

  useEffect(() => {
    if (existing.status === 'success') setForm(toForm(existing.data));
  }, [existing.status, existing.data]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setFieldErrors({});
    setGeneralError(null);
    setSaving(true);
    try {
      const draft = { title: form.title.trim(), goalAmount: Math.round(Number(form.goalAmount) * 100), startsOn: form.startsOn, endsOn: form.endsOn, status: form.status };
      if (isEdit) {
        await volunteeringApi.updateFundraiser(fundraiserId!, draft);
        setSavedOnce(true);
      } else {
        const created = await volunteeringApi.createFundraiser(draft);
        navigate(`/volunteering/${created.id}/edit`, { replace: true });
      }
    } catch (err) {
      const apiErr = err as ApiError;
      if (apiErr.field) setFieldErrors({ [apiErr.field]: apiErr.message });
      else setGeneralError(apiErr.message);
    } finally {
      setSaving(false);
    }
  };

  const submitSale = async (e: FormEvent) => {
    e.preventDefault();
    setSaleError(null);
    setSaleNoteSuccess(false);
    setRecordingSale(true);
    try {
      await volunteeringApi.recordSale(fundraiserId!, { amount: Math.round(Number(saleAmount) * 100), note: saleNote.trim() || undefined });
      setSaleAmount('');
      setSaleNote('');
      setSaleNoteSuccess(true);
      existing.reload();
    } catch (err) {
      setSaleError((err as ApiError).message);
    } finally {
      setRecordingSale(false);
    }
  };

  if (isEdit && existing.status === 'loading') return <Spinner fullPage label="Loading fundraiser…" />;
  if (isEdit && existing.status === 'error') return <ErrorBox error={existing.error!} onRetry={existing.reload} />;

  return (
    <PageShell title={isEdit ? 'Edit Fundraiser' : 'New Fundraiser'}>
      <Panel accent={accentVarForFeature('volunteering')} className={styles.section}>
        <h2 className={styles.sectionTitle}>Fundraiser Details</h2>
        {savedOnce && <p className={styles.successNote}>Saved.</p>}
        {generalError && <ErrorBox error={generalError} />}
        <form onSubmit={submit} noValidate>
          <TextInput label="Title" required value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} error={fieldErrors.title} />
          <TextInput
            label="Goal (₹)"
            type="number"
            min={0}
            step="0.01"
            required
            value={form.goalAmount}
            onChange={(e) => setForm((f) => ({ ...f, goalAmount: e.target.value }))}
            error={fieldErrors.goal_amount ?? fieldErrors.goalAmount}
          />
          <div className={styles.row}>
            <TextInput label="Starts On" type="date" required value={form.startsOn} onChange={(e) => setForm((f) => ({ ...f, startsOn: e.target.value }))} error={fieldErrors.starts_on} />
            <TextInput label="Ends On" type="date" required value={form.endsOn} onChange={(e) => setForm((f) => ({ ...f, endsOn: e.target.value }))} error={fieldErrors.ends_on} />
          </div>
          <SelectInput label="Status" value={form.status} onChange={(e) => setForm((f) => ({ ...f, status: e.target.value as FundraiserStatus }))} options={STATUS_OPTIONS} />
          <button type="submit" className={styles.button} disabled={saving}>
            {saving ? <Spinner size={16} label="Saving" /> : isEdit ? 'Save Changes' : 'Create Fundraiser'}
          </button>
        </form>
      </Panel>

      {isEdit && (
        <Panel accent={accentVarForFeature('volunteering')}>
          <h2 className={styles.sectionTitle}>Record a Sale</h2>
          {saleNoteSuccess && <p className={styles.successNote}>Recorded.</p>}
          {saleError && <ErrorBox error={saleError} />}
          <form onSubmit={submitSale} noValidate style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <TextInput label="Amount (₹)" type="number" min={0} step="0.01" required value={saleAmount} onChange={(e) => setSaleAmount(e.target.value)} />
            <TextInput label="Note" value={saleNote} onChange={(e) => setSaleNote(e.target.value)} />
            <button type="submit" className={styles.button} disabled={recordingSale || !saleAmount}>
              {recordingSale ? <Spinner size={16} label="Recording" /> : 'Record Sale'}
            </button>
          </form>
        </Panel>
      )}
    </PageShell>
  );
}
