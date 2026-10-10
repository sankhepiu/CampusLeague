import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { TextInput } from '../../components/FormField/TextInput';
import { SelectInput } from '../../components/FormField/SelectInput';
import { Money } from '../../components/Money/Money';
import type { ApiError } from '../../api/client';
import { useAsync } from '../../core/hooks/useAsync';
import { accentVarForFeature } from '../../core/config/accents';
import { eventsApi } from './api';
import { fromDatetimeLocalValue, rupeesToPaise, toDatetimeLocalValue } from './eventDateHelpers';
import type { EventItem, EventStatus } from './types';
import styles from './EventAdminPage.module.scss';

const STATUS_OPTIONS: { value: EventStatus; label: string }[] = [
  { value: 'draft', label: 'Draft' },
  { value: 'on_sale', label: 'On Sale' },
  { value: 'closed', label: 'Closed' },
];

// Server field names (snake_case) -> our camelCase form field keys.
const SERVER_FIELD_MAP: Record<string, string> = {
  ends_at: 'endsAt',
  capacity_total: 'capacityTotal',
  budget_amount: 'budgetAmount',
  public_price: 'publicPrice',
  member_price: 'memberPrice',
  sale_opens: 'saleOpens',
  sale_closes: 'saleCloses',
};
const toFormField = (field: string) => SERVER_FIELD_MAP[field] ?? field;

interface EventFormState {
  title: string;
  venue: string;
  startsAt: string;
  endsAt: string;
  capacityTotal: string;
  description: string;
  status: EventStatus;
  budgetAmount: string;
}

const EMPTY_EVENT_FORM: EventFormState = {
  title: '',
  venue: '',
  startsAt: '',
  endsAt: '',
  capacityTotal: '',
  description: '',
  status: 'draft',
  budgetAmount: '0',
};

function eventToForm(event: EventItem): EventFormState {
  return {
    title: event.title,
    venue: event.venue,
    startsAt: toDatetimeLocalValue(event.startsAt),
    endsAt: toDatetimeLocalValue(event.endsAt),
    capacityTotal: String(event.capacityTotal),
    description: event.description,
    status: event.status,
    // budget_amount is write-only per the contract — GET never returns it,
    // so there is nothing to pre-fill. Blank means "leave unchanged" (see
    // submitEvent, which omits it from the PATCH body when blank).
    budgetAmount: '',
  };
}

interface TierFormState {
  name: string;
  publicPrice: string;
  memberPrice: string;
  capacity: string;
  saleOpens: string;
  saleCloses: string;
}

const EMPTY_TIER_FORM: TierFormState = { name: '', publicPrice: '', memberPrice: '', capacity: '', saleOpens: '', saleCloses: '' };

export function EventAdminPage() {
  const { id } = useParams<{ id: string }>();
  const isEdit = id !== undefined;
  const eventId = isEdit ? Number(id) : null;
  const navigate = useNavigate();

  const existing = useAsync(() => eventsApi.get(eventId!), [eventId], { enabled: isEdit });

  const [form, setForm] = useState<EventFormState>(EMPTY_EVENT_FORM);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedOnce, setSavedOnce] = useState(false);

  const [tierForm, setTierForm] = useState<TierFormState>(EMPTY_TIER_FORM);
  const [tierErrors, setTierErrors] = useState<Record<string, string>>({});
  const [tierGeneralError, setTierGeneralError] = useState<string | null>(null);
  const [savingTier, setSavingTier] = useState(false);

  useEffect(() => {
    if (existing.status === 'success') {
      setForm(eventToForm(existing.data));
    }
  }, [existing.status, existing.data]);

  const applyServerError = (err: ApiError, setErrors: (e: Record<string, string>) => void, setGeneral: (m: string | null) => void) => {
    if (err.errors && err.errors.length > 0) {
      const perField: Record<string, string> = {};
      for (const fe of err.errors) perField[toFormField(fe.field)] = fe.message;
      setErrors(perField);
    } else if (err.field) {
      setErrors({ [toFormField(err.field)]: err.message });
    } else {
      setGeneral(err.message);
    }
  };

  const submitEvent = async (e: FormEvent) => {
    e.preventDefault();
    setFieldErrors({});
    setGeneralError(null);
    setSaving(true);
    try {
      const draft = {
        title: form.title.trim(),
        venue: form.venue.trim(),
        startsAt: fromDatetimeLocalValue(form.startsAt),
        endsAt: fromDatetimeLocalValue(form.endsAt),
        capacityTotal: Number(form.capacityTotal),
        description: form.description.trim(),
        status: form.status,
        // Blank means "leave the budget unchanged" — budget_amount is
        // write-only, so we never know the current value to default to.
        ...(form.budgetAmount.trim() !== '' ? { budgetAmount: rupeesToPaise(form.budgetAmount) } : {}),
      };
      if (isEdit) {
        await eventsApi.update(eventId!, draft);
        setSavedOnce(true);
      } else {
        const created = await eventsApi.create(draft);
        navigate(`/events/${created.id}/edit`, { replace: true });
      }
    } catch (err) {
      applyServerError(err as ApiError, setFieldErrors, setGeneralError);
    } finally {
      setSaving(false);
    }
  };

  const submitTier = async (e: FormEvent) => {
    e.preventDefault();
    setTierErrors({});
    setTierGeneralError(null);
    setSavingTier(true);
    try {
      await eventsApi.addTier(eventId!, {
        name: tierForm.name.trim(),
        publicPrice: rupeesToPaise(tierForm.publicPrice),
        memberPrice: rupeesToPaise(tierForm.memberPrice),
        capacity: Number(tierForm.capacity),
        saleOpens: tierForm.saleOpens ? fromDatetimeLocalValue(tierForm.saleOpens) : null,
        saleCloses: tierForm.saleCloses ? fromDatetimeLocalValue(tierForm.saleCloses) : null,
      });
      setTierForm(EMPTY_TIER_FORM);
      existing.reload();
    } catch (err) {
      applyServerError(err as ApiError, setTierErrors, setTierGeneralError);
    } finally {
      setSavingTier(false);
    }
  };

  if (isEdit && existing.status === 'loading') return <Spinner fullPage label="Loading event…" />;
  if (isEdit && existing.status === 'error') return <ErrorBox error={existing.error!} onRetry={existing.reload} />;

  return (
    <PageShell title={isEdit ? 'Edit Event' : 'New Event'}>
      <Panel accent={accentVarForFeature('events')} className={styles.section}>
        <h2 className={styles.sectionTitle}>Event Details</h2>
        {savedOnce && <p className={styles.successNote}>Saved.</p>}
        {generalError && <ErrorBox error={generalError} />}
        <form onSubmit={submitEvent} noValidate>
          <TextInput label="Title" required value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} error={fieldErrors.title} />
          <TextInput label="Venue" required value={form.venue} onChange={(e) => setForm((f) => ({ ...f, venue: e.target.value }))} error={fieldErrors.venue} />
          <div className={styles.row}>
            <TextInput
              label="Starts At"
              type="datetime-local"
              required
              value={form.startsAt}
              onChange={(e) => setForm((f) => ({ ...f, startsAt: e.target.value }))}
              error={fieldErrors.startsAt}
            />
            <TextInput
              label="Ends At"
              type="datetime-local"
              required
              value={form.endsAt}
              onChange={(e) => setForm((f) => ({ ...f, endsAt: e.target.value }))}
              error={fieldErrors.endsAt}
            />
          </div>
          <div className={styles.row}>
            <TextInput
              label="Capacity"
              type="number"
              min={0}
              required
              value={form.capacityTotal}
              onChange={(e) => setForm((f) => ({ ...f, capacityTotal: e.target.value }))}
              error={fieldErrors.capacityTotal}
            />
            <SelectInput label="Status" value={form.status} onChange={(e) => setForm((f) => ({ ...f, status: e.target.value as EventStatus }))} options={STATUS_OPTIONS} />
          </div>
          <TextInput
            label="Budget (₹)"
            type="number"
            min={0}
            step="0.01"
            hint={isEdit ? 'Write-only — leave blank to keep the current budget unchanged.' : 'Converted to paise on save.'}
            value={form.budgetAmount}
            onChange={(e) => setForm((f) => ({ ...f, budgetAmount: e.target.value }))}
            error={fieldErrors.budgetAmount}
          />
          <TextInput label="Description" value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} error={fieldErrors.description} />
          <button type="submit" className={styles.button} disabled={saving}>
            {saving ? <Spinner size={16} label="Saving" /> : isEdit ? 'Save Changes' : 'Create Event'}
          </button>
        </form>
      </Panel>

      {isEdit && existing.status === 'success' && (
        <Panel accent={accentVarForFeature('events')}>
          <h2 className={styles.sectionTitle}>Tiers</h2>

          {existing.data.tiers.length > 0 && (
            <ul className={styles.tierList}>
              {existing.data.tiers.map((tier) => (
                <li key={tier.id} className={styles.tierRow}>
                  <span>
                    {tier.name} ({tier.capacity} seats)
                  </span>
                  <span>
                    <Money paise={tier.publicPrice} /> public / <Money paise={tier.memberPrice} /> member
                  </span>
                </li>
              ))}
            </ul>
          )}

          {tierGeneralError && <ErrorBox error={tierGeneralError} />}
          <form onSubmit={submitTier} noValidate>
            <TextInput label="Tier Name" required value={tierForm.name} onChange={(e) => setTierForm((f) => ({ ...f, name: e.target.value }))} error={tierErrors.name} />
            <div className={styles.row}>
              <TextInput
                label="Public Price (₹)"
                type="number"
                min={0}
                step="0.01"
                required
                value={tierForm.publicPrice}
                onChange={(e) => setTierForm((f) => ({ ...f, publicPrice: e.target.value }))}
                error={tierErrors.publicPrice}
              />
              <TextInput
                label="Member Price (₹)"
                type="number"
                min={0}
                step="0.01"
                required
                value={tierForm.memberPrice}
                onChange={(e) => setTierForm((f) => ({ ...f, memberPrice: e.target.value }))}
                error={tierErrors.memberPrice}
              />
            </div>
            <TextInput
              label="Capacity"
              type="number"
              min={0}
              required
              value={tierForm.capacity}
              onChange={(e) => setTierForm((f) => ({ ...f, capacity: e.target.value }))}
              error={tierErrors.capacity}
            />
            <div className={styles.row}>
              <TextInput
                label="Sale Opens"
                type="datetime-local"
                hint="Optional — leave blank for no limit."
                value={tierForm.saleOpens}
                onChange={(e) => setTierForm((f) => ({ ...f, saleOpens: e.target.value }))}
                error={tierErrors.saleOpens}
              />
              <TextInput
                label="Sale Closes"
                type="datetime-local"
                hint="Optional — leave blank for no limit."
                value={tierForm.saleCloses}
                onChange={(e) => setTierForm((f) => ({ ...f, saleCloses: e.target.value }))}
                error={tierErrors.saleCloses}
              />
            </div>
            <button type="submit" className={styles.button} disabled={savingTier}>
              {savingTier ? <Spinner size={16} label="Adding" /> : 'Add Tier'}
            </button>
          </form>
        </Panel>
      )}
    </PageShell>
  );
}
