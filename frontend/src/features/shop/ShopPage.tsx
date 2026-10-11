import { useState } from 'react';
import { Link } from 'react-router-dom';
import { PageShell } from '../../components/PageShell/PageShell';
import { Panel } from '../../components/Panel/Panel';
import { EmptyState } from '../../components/EmptyState/EmptyState';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { Money } from '../../components/Money/Money';
import { StatusBadge } from '../../components/StatusBadge/StatusBadge';
import { SelectInput } from '../../components/FormField/SelectInput';
import { PixelIcon } from '../../components/PixelIcon';
import { useAsync } from '../../core/hooks/useAsync';
import { useAuth } from '../../core/hooks/useAuth';
import { useCart } from '../../core/hooks/useCart';
import { accentVarForFeature } from '../../core/config/accents';
import { shopApi } from './api';
import type { ProductCategory } from './types';
import styles from './ShopPage.module.scss';

const CATEGORY_FILTER_OPTIONS: { value: ProductCategory | ''; label: string }[] = [
  { value: '', label: 'All categories' },
  { value: 'apparel', label: 'Apparel' },
  { value: 'accessories', label: 'Accessories' },
  { value: 'stationery', label: 'Stationery' },
  { value: 'drinkware', label: 'Drinkware' },
];

export function ShopPage() {
  const { hasRole } = useAuth();
  const { items } = useCart();
  const [page, setPage] = useState(1);
  const [category, setCategory] = useState<ProductCategory | ''>('');
  const { status, data, error, reload } = useAsync(() => shopApi.listProducts(page), [page]);

  const canManage = hasRole('president', 'treasurer', 'event_manager');
  const cartCount = items.reduce((sum, i) => sum + i.quantity, 0);
  const filtered = status === 'success' ? data.results.filter((p) => !category || p.category === category) : [];

  return (
    <PageShell title="Shop" background="dotted">
      <div className={styles.header}>
        {canManage && (
          <Link to="/shop/new" className={`${styles.headerButton} ${styles.headerButtonSecondary}`}>
            + New Product
          </Link>
        )}
        <Link to="/shop/cart" className={styles.headerButton}>
          Cart{cartCount > 0 ? ` (${cartCount})` : ''}
        </Link>
      </div>

      <div className={styles.filterRow}>
        <SelectInput label="Category" value={category} onChange={(e) => setCategory(e.target.value as ProductCategory | '')} options={CATEGORY_FILTER_OPTIONS} />
      </div>

      {status === 'loading' && <Spinner fullPage label="Loading products…" />}
      {status === 'error' && <ErrorBox error={error!} onRetry={reload} />}
      {status === 'success' && filtered.length === 0 && (
        <Panel>
          <EmptyState icon="chest" title="No products yet" message="Check back once the shop is stocked." />
        </Panel>
      )}

      {status === 'success' && filtered.length > 0 && (
        <>
          <div className={styles.grid}>
            {filtered.map((product) => {
              const onSale = product.salePct > 0;
              const allSoldOut = product.sizes.every((s) => s.stock === 0);
              return (
                <Link key={product.id} to={`/shop/${product.id}`} className={styles.card}>
                  <Panel accent={accentVarForFeature('shop')}>
                    {product.imageUrl ? (
                      <img src={product.imageUrl} alt={product.name} className={styles.productImage} loading="lazy" />
                    ) : (
                      <div className={styles.imagePlaceholder}>
                        <PixelIcon name="chest" size={40} />
                      </div>
                    )}
                    {onSale && (
                      <div className={styles.saleBadge}>
                        <StatusBadge variant="danger">-{product.salePct}%</StatusBadge>
                      </div>
                    )}
                    <h3 className={styles.name}>{product.name}</h3>
                    <div className={styles.priceRow}>
                      <Money paise={product.price} />
                      {product.price < product.basePrice && <span className={styles.strike}>₹{(product.basePrice / 100).toFixed(2)}</span>}
                    </div>
                    {!product.active && (
                      <div className={styles.inactiveBadge}>
                        <StatusBadge variant="warning">Inactive (staff only)</StatusBadge>
                      </div>
                    )}
                    {product.active && allSoldOut && (
                      <div className={styles.inactiveBadge}>
                        <StatusBadge variant="danger">Sold out</StatusBadge>
                      </div>
                    )}
                  </Panel>
                </Link>
              );
            })}
          </div>

          <div className={styles.pagination}>
            <button type="button" className={styles.pageButton} onClick={() => setPage((p) => p - 1)} disabled={!data.previous}>
              ← Previous
            </button>
            <button type="button" className={styles.pageButton} onClick={() => setPage((p) => p + 1)} disabled={!data.next}>
              Next →
            </button>
          </div>
        </>
      )}
    </PageShell>
  );
}
