import { useState, type FormEvent } from 'react';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { EmptyState } from '../../components/EmptyState/EmptyState';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { StatusBadge } from '../../components/StatusBadge/StatusBadge';
import { TextInput } from '../../components/FormField/TextInput';
import { SelectInput } from '../../components/FormField/SelectInput';
import type { ApiError } from '../../api/client';
import { useAsync } from '../../core/hooks/useAsync';
import { accentVarForFeature } from '../../core/config/accents';
import { couponsApi } from './api';
import type { Coupon, CouponAppliesTo, CouponDraft, CouponKind } from './types';
import styles from './CouponAdminPage.module.scss';

const KIND_OPTIONS: { value: CouponKind; label: string }[] = [
  { value: 'percent', label: 'Percent off' },
  { value: 'flat', label: 'Flat amount off' },
];

const APPLIES_OPTIONS: { value: CouponAppliesTo; label: string }[] = [
  { value: 'all', label: 'Everything' },
  { value: 'merch', label: 'Shop only' },
  { value: 'tickets', label: 'Tickets only' },
  { value: 'membership', label: 'Membership only' },
];

interface CouponFormState {
  code: string;
  kind: CouponKind;
  value: string;
  minOrder: string;
  maxDiscount: string;
  usageLimit: string;
  perUserLimit: string;
  appliesTo: CouponAppliesTo;
  validFrom: string;
  validTo: string;
}

const EMPTY_FORM: CouponFormState = {
  code: '',
  kind: 'percent',
  value: '',
  minOrder: '0',
  maxDiscount: '',
  usageLimit: '',
  perUserLimit: '1',
  appliesTo: 'all',
  validFrom: '',
  validTo: '',
};

function validateForm(form: CouponFormState): Record<string, string> {
  const errors: Record<string, string> = {};
  const code = form.code.trim();
  if (!/^[A-Za-z0-9_-]{3,20}$/.test(code)) errors.code = 'Must be 3 to 20 letters, digits, - or _.';

  const value = Number(form.value);
  if (!form.value || Number.isNaN(value)) errors.value = 'Required.';
  else if (form.kind === 'percent' && (value < 1 || value > 100)) errors.value = 'A percent coupon must be 1 to 100.';
  else if (form.kind === 'flat' && (value < 1 || value > 1_000_000_000)) errors.value = 'Must be greater than zero.';

  if (form.minOrder !== '' && (Number.isNaN(Number(form.minOrder)) || Number(form.minOrder) < 0)) errors.minOrder = 'Must be zero or more.';
  if (form.maxDiscount !== '' && (Number.isNaN(Number(form.maxDiscount)) || Number(form.maxDiscount) < 0)) errors.maxDiscount = 'Must be zero or more.';
  if (form.usageLimit !== '' && (Number.isNaN(Number(form.usageLimit)) || Number(form.usageLimit) < 1)) errors.usageLimit = 'Must be at least 1.';
  if (form.perUserLimit !== '' && (Number.isNaN(Number(form.perUserLimit)) || Number(form.perUserLimit) < 1)) errors.perUserLimit = 'Must be at least 1.';
  if (form.validFrom && form.validTo && form.validTo <= form.validFrom) errors.validTo = 'Must be after valid-from.';
  return errors;
}

function formToDraft(form: CouponFormState): CouponDraft {
  return {
    code: form.code.trim().toUpperCase(),
    kind: form.kind,
    value: form.kind === 'percent' ? Number(form.value) : Math.round(Number(form.value) * 100),
    minOrder: form.minOrder ? Math.round(Number(form.minOrder) * 100) : 0,
    maxDiscount: form.maxDiscount ? Math.round(Number(form.maxDiscount) * 100) : null,
    usageLimit: form.usageLimit ? Number(form.usageLimit) : null,
    perUserLimit: form.perUserLimit ? Number(form.perUserLimit) : 1,
    appliesTo: form.appliesTo,
    validFrom: form.validFrom || null,
    validTo: form.validTo || null,
  };
}

export function CouponAdminPage() {
  const { status, data, error, reload } = useAsync(() => couponsApi.list(), []);
  const [form, setForm] = useState<CouponFormState>(EMPTY_FORM);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setGeneralError(null);
    const errors = validateForm(form);
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;
    setSaving(true);
    try {
      await couponsApi.create(formToDraft(form));
      setForm(EMPTY_FORM);
      reload();
    } catch (err) {
      const apiErr = err as ApiError;
      if (apiErr.field) setFieldErrors({ [apiErr.field]: apiErr.message });
      else setGeneralError(apiErr.message);
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (coupon: Coupon) => {
    await couponsApi.update(coupon.id, { active: !coupon.active });
    reload();
  };

  const remove = async (coupon: Coupon) => {
    try {
      await couponsApi.remove(coupon.id);
      reload();
    } catch (err) {
      setGeneralError((err as ApiError).message);
    }
  };

  return (
    <PageShell title="Coupons">
      <Panel accent={accentVarForFeature('couponAdmin')} className={styles.formPanel}>
        <h2 className={styles.sectionTitle}>New Coupon</h2>
        {generalError && <ErrorBox error={generalError} />}
        <form onSubmit={submit} noValidate className={styles.form}>
          <TextInput label="Code" required value={form.code} onChange={(e) => setForm((f) => ({ ...f, code: e.target.value.toUpperCase() }))} error={fieldErrors.code} />
          <SelectInput label="Kind" value={form.kind} onChange={(e) => setForm((f) => ({ ...f, kind: e.target.value as CouponKind }))} options={KIND_OPTIONS} />
          <TextInput
            label={form.kind === 'percent' ? 'Value (%)' : 'Value (₹)'}
            type="number"
            min={0}
            step={form.kind === 'percent' ? 1 : 0.01}
            required
            value={form.value}
            onChange={(e) => setForm((f) => ({ ...f, value: e.target.value }))}
            error={fieldErrors.value}
          />
          <SelectInput label="Applies to" value={form.appliesTo} onChange={(e) => setForm((f) => ({ ...f, appliesTo: e.target.value as CouponAppliesTo }))} options={APPLIES_OPTIONS} />
          <TextInput label="Min order (₹)" type="number" min={0} step="0.01" value={form.minOrder} onChange={(e) => setForm((f) => ({ ...f, minOrder: e.target.value }))} error={fieldErrors.minOrder} />
          <TextInput label="Max discount (₹, blank = no cap)" type="number" min={0} step="0.01" value={form.maxDiscount} onChange={(e) => setForm((f) => ({ ...f, maxDiscount: e.target.value }))} error={fieldErrors.maxDiscount} />
          <TextInput label="Usage limit (blank = unlimited)" type="number" min={1} value={form.usageLimit} onChange={(e) => setForm((f) => ({ ...f, usageLimit: e.target.value }))} error={fieldErrors.usageLimit} />
          <TextInput label="Per-user limit" type="number" min={1} value={form.perUserLimit} onChange={(e) => setForm((f) => ({ ...f, perUserLimit: e.target.value }))} error={fieldErrors.perUserLimit} />
          <TextInput label="Valid from" type="date" value={form.validFrom} onChange={(e) => setForm((f) => ({ ...f, validFrom: e.target.value }))} />
          <TextInput label="Valid to" type="date" value={form.validTo} onChange={(e) => setForm((f) => ({ ...f, validTo: e.target.value }))} error={fieldErrors.validTo} />
          <button type="submit" className={styles.button} disabled={saving}>
            {saving ? <Spinner size={16} label="Saving" /> : 'Create Coupon'}
          </button>
        </form>
      </Panel>

      <h2 className={styles.sectionTitle}>Existing Coupons</h2>
      {status === 'loading' && <Spinner fullPage label="Loading coupons…" />}
      {status === 'error' && <ErrorBox error={error!} onRetry={reload} />}
      {status === 'success' && data.results.length === 0 && (
        <Panel>
          <EmptyState icon="coin" title="No coupons yet" message="Create one above." />
        </Panel>
      )}

      {status === 'success' && data.results.length > 0 && (
        <div className={styles.list}>
          {data.results.map((coupon) => (
            <Panel key={coupon.id} accent={accentVarForFeature('couponAdmin')}>
              <div className={styles.row}>
                <div>
                  <h3 className={styles.code}>{coupon.code}</h3>
                  <p className={styles.meta}>
                    {coupon.kind === 'percent' ? `${coupon.value}% off` : `₹${(coupon.value / 100).toFixed(2)} off`} · {coupon.appliesTo} · used {coupon.usedCount}
                    {coupon.usageLimit !== null ? ` / ${coupon.usageLimit}` : ''}
                  </p>
                  <p className={styles.meta}>
                    Min order ₹{(coupon.minOrder / 100).toFixed(2)}
                    {coupon.maxDiscount !== null && ` · Max discount ₹${(coupon.maxDiscount / 100).toFixed(2)}`} · {coupon.perUserLimit} per user
                  </p>
                </div>
                <StatusBadge variant={coupon.active ? 'success' : 'neutral'}>{coupon.active ? 'Active' : 'Inactive'}</StatusBadge>
              </div>
              <div className={styles.actions}>
                <button type="button" className={styles.smallButton} onClick={() => toggleActive(coupon)}>
                  {coupon.active ? 'Deactivate' : 'Activate'}
                </button>
                {coupon.usedCount === 0 && (
                  <button type="button" className={`${styles.smallButton} ${styles.smallButtonDanger}`} onClick={() => remove(coupon)}>
                    Delete
                  </button>
                )}
              </div>
            </Panel>
          ))}
        </div>
      )}
    </PageShell>
  );
}
