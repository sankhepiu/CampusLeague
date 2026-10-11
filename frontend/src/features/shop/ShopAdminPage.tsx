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
import type { Product, ProductCategory, SizeLabel } from './types';
import styles from './ShopAdminPage.module.scss';

const SIZE_OPTIONS: { value: SizeLabel; label: string }[] = [
  { value: 'S', label: 'S' },
  { value: 'M', label: 'M' },
  { value: 'L', label: 'L' },
  { value: 'XL', label: 'XL' },
];

const CATEGORY_OPTIONS: { value: ProductCategory; label: string }[] = [
  { value: 'apparel', label: 'Apparel' },
  { value: 'accessories', label: 'Accessories' },
  { value: 'stationery', label: 'Stationery' },
  { value: 'drinkware', label: 'Drinkware' },
];

interface ProductFormState {
  name: string;
  basePrice: string;
  description: string;
  category: ProductCategory;
  salePct: string;
  active: boolean;
}

const EMPTY_FORM: ProductFormState = { name: '', basePrice: '', description: '', category: 'apparel', salePct: '0', active: true };

function productToForm(p: Product): ProductFormState {
  return { name: p.name, basePrice: (p.basePrice / 100).toString(), description: p.description, category: p.category, salePct: String(p.salePct), active: p.active };
}

function validateProductForm(form: ProductFormState): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!form.name.trim()) errors.name = 'This field is required.';
  else if (form.name.trim().length > 100) errors.name = 'Must be 100 characters or fewer.';
  const price = Number(form.basePrice);
  if (!form.basePrice || Number.isNaN(price) || price <= 0) errors.basePrice = 'Must be greater than zero.';
  else if (Math.round(price * 100) > 1_000_000_000) errors.basePrice = 'That is too large.';
  if (form.description.length > 2000) errors.description = 'Must be 2,000 characters or fewer.';
  const salePct = Number(form.salePct);
  if (form.salePct !== '' && (Number.isNaN(salePct) || salePct < 0 || salePct > 90)) errors.salePct = 'Must be 0 to 90.';
  return errors;
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
    setGeneralError(null);
    const clientErrors = validateProductForm(form);
    setFieldErrors(clientErrors);
    if (Object.keys(clientErrors).length > 0) return;
    setSaving(true);
    try {
      const draft = {
        name: form.name.trim(),
        basePrice: Math.round(Number(form.basePrice) * 100),
        description: form.description.trim(),
        category: form.category,
        salePct: Number(form.salePct) || 0,
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
    const qty = Number(restockQty);
    if (!restockQty || Number.isNaN(qty) || qty < 1 || qty > 10000) {
      setRestockError('Quantity must be between 1 and 10,000.');
      return;
    }
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

  const currentImageUrl = existing.status === 'success' ? existing.data.imageUrl : null;

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
          <SelectInput
            label="Category"
            value={form.category}
            onChange={(e) => setForm((f) => ({ ...f, category: e.target.value as ProductCategory }))}
            options={CATEGORY_OPTIONS}
          />
          <TextInput
            label="Sale % (0 = not on sale)"
            type="number"
            min={0}
            max={90}
            value={form.salePct}
            onChange={(e) => setForm((f) => ({ ...f, salePct: e.target.value }))}
            error={fieldErrors.salePct ?? fieldErrors.sale_pct}
          />
          {/* The picture is read-only: the contract has no upload endpoint,
              the server supplies `image_url` (the seed's pixel art). */}
          <div className={styles.imageRow}>
            {currentImageUrl ? (
              <img src={currentImageUrl} alt="Current product picture" className={styles.imagePreview} />
            ) : (
              <span className={styles.imageNone}>No picture</span>
            )}
            <span className={styles.imageNote}>Pictures are supplied by the server. Uploading one isn't supported yet.</span>
          </div>
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
