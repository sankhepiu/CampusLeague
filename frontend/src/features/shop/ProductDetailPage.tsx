import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { PageShell } from '../../components/PageShell/PageShell';
import { ErrorBox } from '../../components/ErrorBox/ErrorBox';
import { Spinner } from '../../components/Spinner/Spinner';
import { Money } from '../../components/Money/Money';
import { StatusBadge } from '../../components/StatusBadge/StatusBadge';
import { PixelIcon } from '../../components/PixelIcon';
import { useAsync } from '../../core/hooks/useAsync';
import { useAuth } from '../../core/hooks/useAuth';
import { useCart } from '../../core/hooks/useCart';
import { shopApi } from './api';
import type { ProductSize } from './types';
import { LIMIT_REACHED_MESSAGE, MAX_PER_ITEM, limitNote } from './limits';
import styles from './ProductDetailPage.module.scss';

const LOW_STOCK_THRESHOLD = 3;

export function ProductDetailPage() {
  const { id } = useParams<{ id: string }>();
  const productId = Number(id);
  const { user, hasRole } = useAuth();
  const { addItem, items: cartItems } = useCart();

  const { status, data: product, error, reload } = useAsync(() => shopApi.getProduct(productId), [productId]);
  const [selectedSize, setSelectedSize] = useState<ProductSize | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [addedNote, setAddedNote] = useState<string | null>(null);

  const canManage = hasRole('president', 'treasurer', 'event_manager');

  if (status === 'loading') return <Spinner fullPage label="Loading product…" />;
  if (status === 'error') return <ErrorBox error={error!} onRetry={reload} />;
  if (!product) return null;

  const onSale = product.salePct > 0;
  const salePrice = product.basePrice - Math.floor((product.basePrice * product.salePct) / 100);

  // The limit of 10 is on the total: what is already in the cart for this
  // size plus what is being added now.
  const inCart = selectedSize ? (cartItems.find((i) => i.productSizeId === selectedSize.id)?.quantity ?? 0) : 0;
  const canAdd = selectedSize ? Math.max(0, Math.min(MAX_PER_ITEM - inCart, selectedSize.stock)) : 0;
  const atLimit = inCart >= MAX_PER_ITEM;
  // Never more than can still be added, even if the cart changed since the
  // stepper was last touched.
  const quantityToAdd = Math.min(quantity, Math.max(1, canAdd));

  const selectSize = (size: ProductSize) => {
    if (size.stock === 0) return;
    setSelectedSize(size);
    setQuantity(1);
    setAddedNote(null);
  };

  const addToCart = () => {
    if (!selectedSize || !product) return;
    const result = addItem(
      {
        productSizeId: selectedSize.id,
        productId: product.id,
        productName: product.name,
        productImage: product.imageUrl,
        sizeLabel: selectedSize.size,
        unitPriceEstimate: product.price,
        unitBasePriceEstimate: product.basePrice,
        unitSalePriceEstimate: salePrice,
      },
      quantityToAdd,
    );
    setAddedNote(
      result.ok
        ? `Added ${result.added} × ${selectedSize.size} to your cart.${result.reason ? ` ${result.reason}` : ''}`
        : (result.reason ?? 'Could not add to cart.'),
    );
    setQuantity(1);
  };

  return (
    <PageShell title={product.name} background="dotted">
      <div className={styles.layout}>
        <div>
          {product.imageUrl ? (
            <img src={product.imageUrl} alt={product.name} className={styles.productImage} />
          ) : (
            <div className={styles.imagePlaceholder}>
              <PixelIcon name="chest" size={72} />
            </div>
          )}
        </div>

        <div>
          <div className={styles.priceRow}>
            <span className={styles.price}>
              <Money paise={product.price} />
            </span>
            {product.price < product.basePrice && (
              <span className={styles.strike}>
                <Money paise={product.basePrice} />
              </span>
            )}
            {onSale && <StatusBadge variant="danger">-{product.salePct}% Sale</StatusBadge>}
            {product.price < salePrice && <StatusBadge variant="info">Member price</StatusBadge>}
          </div>

          {!product.active && (
            <div style={{ marginBottom: '1rem' }}>
              <StatusBadge variant="warning">Inactive — staff only</StatusBadge>
              {canManage && (
                <>
                  {' '}
                  <Link to={`/shop/${product.id}/edit`}>Edit</Link>
                </>
              )}
            </div>
          )}
          {product.active && canManage && (
            <p style={{ marginBottom: '1rem' }}>
              <Link to={`/shop/${product.id}/edit`}>Edit Product</Link>
            </p>
          )}

          {product.description && <p className={styles.description}>{product.description}</p>}

          <div className={styles.sizeGrid}>
            {product.sizes.map((size) => (
              <button
                key={size.id}
                type="button"
                className={`${styles.sizeButton} ${selectedSize?.id === size.id ? styles.sizeButtonActive : ''}`}
                disabled={size.stock === 0}
                onClick={() => selectSize(size)}
              >
                {size.stock === 0 ? `${size.size} — Sold out` : size.size}
              </button>
            ))}
          </div>

          {selectedSize && (
            <p className={`${styles.stockNote} ${selectedSize.stock <= LOW_STOCK_THRESHOLD ? styles.lowStock : ''}`}>
              {selectedSize.stock <= LOW_STOCK_THRESHOLD ? `Only ${selectedSize.stock} left` : `${selectedSize.stock} in stock`}
            </p>
          )}

          {selectedSize && (
            <>
              <div className={styles.quantityRow}>
                <span>Quantity</span>
                <button
                  type="button"
                  className={styles.qtyButton}
                  onClick={() => setQuantity(Math.max(1, quantityToAdd - 1))}
                  disabled={quantityToAdd <= 1 || atLimit}
                >
                  −
                </button>
                <span>{atLimit ? 0 : quantityToAdd}</span>
                <button
                  type="button"
                  className={styles.qtyButton}
                  onClick={() => setQuantity(Math.min(canAdd, quantityToAdd + 1))}
                  disabled={quantityToAdd >= canAdd}
                >
                  +
                </button>
              </div>

              <p className={styles.stockNote}>{atLimit ? LIMIT_REACHED_MESSAGE : limitNote(inCart)}</p>

              <button
                type="button"
                className={styles.addButton}
                disabled={!user || atLimit || canAdd === 0}
                onClick={addToCart}
                title={!user ? 'Log in to add items to your cart' : atLimit ? LIMIT_REACHED_MESSAGE : undefined}
              >
                Add to Cart
              </button>
              {!user && <p className={styles.stockNote}>Log in to add items to your cart.</p>}
              {addedNote && (
                <p className={styles.addedNote}>
                  {addedNote} <Link to="/shop/cart">View Cart</Link>
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </PageShell>
  );
}
