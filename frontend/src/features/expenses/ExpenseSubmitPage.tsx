import { useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { TextInput } from '../../components/FormField/TextInput';
import { SelectInput } from '../../components/FormField/SelectInput';
import type { ApiError } from '../../api/client';
import { useAsync } from '../../core/hooks/useAsync';
import { accentVarForFeature } from '../../core/config/accents';
import { eventsApi } from '../events/api';
import { volunteeringApi } from '../volunteering/api';
import { expensesApi } from './api';
import { validateReceiptFile } from './receiptValidation';
import type { Expense, ExpenseCategory } from './types';
import styles from './ExpenseSubmitPage.module.scss';

const CATEGORY_OPTIONS: { value: ExpenseCategory; label: string }[] = [
  { value: 'general', label: 'General' },
  { value: 'event', label: 'Event' },
  { value: 'fundraiser', label: 'Fundraiser' },
];
const DESCRIPTION_MAX = 500;

export function ExpenseSubmitPage() {
  const eventsState = useAsync(() => eventsApi.list(1), []);
  const fundraisersState = useAsync(() => volunteeringApi.listFundraisers(1), []);

  const [amount, setAmount] = useState('');
  const [category, setCategory] = useState<ExpenseCategory>('general');
  const [eventId, setEventId] = useState('');
  const [fundraiserId, setFundraiserId] = useState('');
  const [description, setDescription] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<Expense | null>(null);

  useEffect(() => {
    if (!file) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const onFileChange = (f: File | null) => {
    setFile(f);
    setFieldErrors((prev) => {
      const next = { ...prev };
      delete next.receipt_file;
      return next;
    });
    if (f) {
      const err = validateReceiptFile(f);
      if (err) setFieldErrors((prev) => ({ ...prev, receipt_file: err.message }));
    }
  };

  const validate = (): Record<string, string> => {
    const errors: Record<string, string> = {};
    const amountPaise = Math.round(Number(amount) * 100);
    if (!amount || amountPaise <= 0) errors.amount = 'Enter an amount greater than zero.';
    if (!description.trim()) errors.description = 'Description is required.';
    else if (description.length > DESCRIPTION_MAX) errors.description = `Description must be ${DESCRIPTION_MAX} characters or fewer.`;
    if (!file) errors.receipt_file = 'A receipt is required.';
    else {
      const fileErr = validateReceiptFile(file);
      if (fileErr) errors.receipt_file = fileErr.message;
    }
    if (category === 'event' && !eventId) errors.event = 'Select the event this expense is for.';
    if (category === 'fundraiser' && !fundraiserId) errors.fundraiser = 'Select the fundraiser this expense is for.';
    return errors;
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const errors = validate();
    setFieldErrors(errors);
    setGeneralError(null);
    if (Object.keys(errors).length > 0 || !file) return;

    setSubmitting(true);
    try {
      const expense = await expensesApi.submit({
        amountPaise: Math.round(Number(amount) * 100),
        category,
        description: description.trim(),
        receiptFile: file,
        ...(category === 'event' ? { event: Number(eventId) } : {}),
        ...(category === 'fundraiser' ? { fundraiser: Number(fundraiserId) } : {}),
      });
      setResult(expense);
    } catch (err) {
      const apiErr = err as ApiError;
      if (apiErr.errors && apiErr.errors.length > 0) {
        const perField: Record<string, string> = {};
        for (const fe of apiErr.errors) perField[fe.field] = fe.message;
        setFieldErrors(perField);
      } else if (apiErr.field) {
        setFieldErrors({ [apiErr.field]: apiErr.message });
      } else {
        setGeneralError(apiErr.message);
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (result) {
    return (
      <PageShell title="Request Submitted">
        <Panel accent="var(--cl-green)" className={styles.successBox}>
          <p>
            <strong>Submitted.</strong> Your request is awaiting approval.
          </p>
          <Link to="/expenses" className={styles.linkButton}>
            View My Requests
          </Link>
          <Link to="/expenses/new" className={styles.linkButton} onClick={() => setResult(null)}>
            Submit Another
          </Link>
        </Panel>
      </PageShell>
    );
  }

  return (
    <PageShell title="Submit Reimbursement">
      <Panel accent={accentVarForFeature('expenses')}>
        {generalError && <ErrorBox error={generalError} />}
        <form onSubmit={submit} noValidate>
          <TextInput label="Amount (₹)" type="number" min={0} step="0.01" required value={amount} onChange={(e) => setAmount(e.target.value)} error={fieldErrors.amount} />

          <SelectInput
            label="Category"
            value={category}
            onChange={(e) => {
              setCategory(e.target.value as ExpenseCategory);
              setEventId('');
              setFundraiserId('');
            }}
            options={CATEGORY_OPTIONS}
          />

          {category === 'event' && eventsState.status === 'success' && (
            <SelectInput
              label="Event"
              required
              value={eventId}
              onChange={(e) => setEventId(e.target.value)}
              options={[{ value: '', label: 'Choose…' }, ...eventsState.data.results.map((ev) => ({ value: String(ev.id), label: ev.title }))]}
              error={fieldErrors.event}
            />
          )}
          {category === 'fundraiser' && fundraisersState.status === 'success' && (
            <SelectInput
              label="Fundraiser"
              required
              value={fundraiserId}
              onChange={(e) => setFundraiserId(e.target.value)}
              options={[{ value: '', label: 'Choose…' }, ...fundraisersState.data.results.map((f) => ({ value: String(f.id), label: f.title }))]}
              error={fieldErrors.fundraiser}
            />
          )}

          <TextInput
            label="Description"
            required
            maxLength={DESCRIPTION_MAX}
            hint={`${description.length}/${DESCRIPTION_MAX} characters`}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            error={fieldErrors.description}
          />

          <div className={styles.fileRow}>
            <label className={styles.label} htmlFor="receipt-file">
              Receipt <span style={{ color: 'var(--cl-color-danger)' }}>*</span>
            </label>
            <input
              id="receipt-file"
              type="file"
              accept="image/jpeg,image/png,application/pdf"
              onChange={(e) => onFileChange(e.target.files?.[0] ?? null)}
              aria-invalid={!!fieldErrors.receipt_file}
            />
            <p className={styles.hint}>JPG, PNG or PDF, up to 5 MB.</p>
            {fieldErrors.receipt_file && <p className={styles.error}>{fieldErrors.receipt_file}</p>}
            {file && previewUrl && (
              <div className={styles.preview}>
                {file.type === 'application/pdf' ? <div className={styles.previewPdf}>PDF</div> : <img src={previewUrl} alt="Receipt preview" className={styles.previewImage} />}
                <span className={styles.hint}>
                  {file.name} ({(file.size / 1024).toFixed(0)} KB)
                </span>
              </div>
            )}
          </div>

          <button type="submit" className={styles.button} disabled={submitting}>
            {submitting ? <Spinner size={16} label="Submitting" /> : 'Submit Request'}
          </button>
        </form>
      </Panel>
    </PageShell>
  );
}
