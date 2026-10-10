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
import { shopApi } from './api';
import type { Product, SizeLabel } from './types';
import styles from './ShopAdminPage.module.scss';

const SIZE_OPTIONS: { value: SizeLabel; label: string }[] = [
  { value: 'S', label: 'S' },
  { value: 'M', label: 'M' },
  { value: 'L', label: 'L' },
  { value: 'XL', label: 'XL' },
];

interface ProductFormState {
  name: string;
  basePrice: string;
  description: string;
  image: string;
  active: boolean;
}

const EMPTY_FORM: ProductFormState = { name: '', basePrice: '', description: '', image: '', active: true };

function productToForm(p: Product): ProductFormState {
  return { name: p.name, basePrice: (p.basePrice / 100).toString(), description: p.description, image: p.image, active: p.active };
}

export function ShopAdminPage() {
  const { id } = useParams<{ id: string }>();
  const isEdit = id !== undefined;
  const productId = isEdit ? Number(id) : null;
  const navigate = useNavigate();

  const existing = useAsync(() => shopApi.getProduct(productId!), [productId], { enabled: isEdit });

  const [form, setForm] = useState<ProductFormState>(EMPTY_FORM);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedOnce, setSavedOnce] = useState(false);

  const [restockSize, setRestockSize] = useState<SizeLabel>('S');
  const [restockQty, setRestockQty] = useState('1');
  const [restockError, setRestockError] = useState<string | null>(null);
  const [restocking, setRestocking] = useState(false);

  useEffect(() => {
    if (existing.status === 'success') setForm(productToForm(existing.data));
  }, [existing.status, existing.data]);

  const applyServerError = (err: ApiError) => {
    if (err.errors && err.errors.length > 0) {
      const perField: Record<string, string> = {};
      for (const fe of err.errors) perField[fe.field] = fe.message;
      setFieldErrors(perField);
    } else if (err.field) {
      setFieldErrors({ [err.field]: err.message });
    } else {
      setGeneralError(err.message);
    }
  };

  const submitProduct = async (e: FormEvent) => {
    e.preventDefault();
    setFieldErrors({});
    setGeneralError(null);
    setSaving(true);
    try {
      const draft = {
        name: form.name.trim(),
        basePrice: Math.round(Number(form.basePrice) * 100),
        description: form.description.trim(),
        image: form.image.trim(),
        active: form.active,
      };
      if (isEdit) {
        await shopApi.updateProduct(productId!, draft);
        setSavedOnce(true);
      } else {
        const created = await shopApi.createProduct(draft);
        navigate(`/shop/${created.id}/edit`, { replace: true });
      }
    } catch (err) {
      applyServerError(err as ApiError);
    } finally {
      setSaving(false);
    }
  };

  const submitRestock = async (e: FormEvent) => {
    e.preventDefault();
    setRestockError(null);
    setRestocking(true);
    try {
      await shopApi.restock(productId!, { size: restockSize, quantity: Number(restockQty) });
      existing.reload();
      setRestockQty('1');
    } catch (err) {
      setRestockError((err as ApiError).message);
    } finally {
      setRestocking(false);
    }
  };

  if (isEdit && existing.status === 'loading') return <Spinner fullPage label="Loading product…" />;
  if (isEdit && existing.status === 'error') return <ErrorBox error={existing.error!} onRetry={existing.reload} />;

  return (
    <PageShell title={isEdit ? 'Edit Product' : 'New Product'}>
      <Panel accent={accentVarForFeature('shop')} className={styles.section}>
        <h2 className={styles.sectionTitle}>Product Details</h2>
        {savedOnce && <p className={styles.successNote}>Saved.</p>}
        {generalError && <ErrorBox error={generalError} />}
        <form onSubmit={submitProduct} noValidate>
          <TextInput label="Name" required value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} error={fieldErrors.name} />
          <TextInput
            label="Base Price (₹)"
            type="number"
            min={0}
            step="0.01"
            required
            value={form.basePrice}
            onChange={(e) => setForm((f) => ({ ...f, basePrice: e.target.value }))}
            error={fieldErrors.base_price ?? fieldErrors.basePrice}
          />
          <TextInput label="Description" value={form.description} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))} error={fieldErrors.description} />
          <TextInput
            label="Image URL"
            hint="Optional — leave blank to show the placeholder icon."
            value={form.image}
            onChange={(e) => setForm((f) => ({ ...f, image: e.target.value }))}
            error={fieldErrors.image}
          />
          <label className={styles.checkboxRow}>
            <input type="checkbox" checked={form.active} onChange={(e) => setForm((f) => ({ ...f, active: e.target.checked }))} />
            Active (visible to everyone)
          </label>
          <button type="submit" className={styles.button} disabled={saving}>
            {saving ? <Spinner size={16} label="Saving" /> : isEdit ? 'Save Changes' : 'Create Product'}
          </button>
        </form>
      </Panel>

      {isEdit && existing.status === 'success' && (
        <Panel accent={accentVarForFeature('shop')}>
          <h2 className={styles.sectionTitle}>Stock</h2>
          <table className={styles.stockTable}>
            <thead>
              <tr>
                <th>Size</th>
                <th>Stock</th>
              </tr>
            </thead>
            <tbody>
              {existing.data.sizes.map((s) => (
                <tr key={s.id}>
                  <td>{s.size}</td>
                  <td>{s.stock}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {restockError && <ErrorBox error={restockError} />}
          <form onSubmit={submitRestock} noValidate style={{ display: 'flex', gap: '1rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
            <SelectInput label="Size" value={restockSize} onChange={(e) => setRestockSize(e.target.value as SizeLabel)} options={SIZE_OPTIONS} />
            <TextInput label="Add Quantity" type="number" min={1} max={10000} value={restockQty} onChange={(e) => setRestockQty(e.target.value)} />
            <button type="submit" className={styles.button} disabled={restocking}>
              {restocking ? <Spinner size={16} label="Restocking" /> : 'Restock'}
            </button>
          </form>
        </Panel>
      )}
    </PageShell>
  );
}
