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
import styles from './ProductDetailPage.module.scss';

const LOW_STOCK_THRESHOLD = 3;

export function ProductDetailPage() {
  const { id } = useParams<{ id: string }>();
  const productId = Number(id);
  const { user, hasRole } = useAuth();
  const { addItem } = useCart();

  const { status, data: product, error, reload } = useAsync(() => shopApi.getProduct(productId), [productId]);
  const [selectedSize, setSelectedSize] = useState<ProductSize | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [addedNote, setAddedNote] = useState<string | null>(null);

  const canManage = hasRole('president', 'treasurer', 'event_manager');

  if (status === 'loading') return <Spinner fullPage label="Loading product…" />;
  if (status === 'error') return <ErrorBox error={error!} onRetry={reload} />;
  if (!product) return null;

  const onSale = product.price < product.basePrice;

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
        productImage: product.image,
        sizeLabel: selectedSize.size,
        unitPriceEstimate: product.price,
      },
      quantity,
    );
    setAddedNote(result.ok ? `Added ${quantity} × ${selectedSize.size} to your cart.` : (result.reason ?? 'Could not add to cart.'));
  };

  return (
    <PageShell title={product.name} background="dotted">
      <div className={styles.layout}>
        <div>
          {product.image ? (
            <img src={product.image} alt={product.name} className={styles.productImage} />
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
            {onSale && (
              <span className={styles.strike}>
                <Money paise={product.basePrice} />
              </span>
            )}
            {onSale && <StatusBadge variant="info">Member price</StatusBadge>}
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
                <button type="button" className={styles.qtyButton} onClick={() => setQuantity((q) => Math.max(1, q - 1))} disabled={quantity <= 1}>
                  −
                </button>
                <span>{quantity}</span>
                <button
                  type="button"
                  className={styles.qtyButton}
                  onClick={() => setQuantity((q) => Math.min(10, q + 1, selectedSize.stock))}
                  disabled={quantity >= 10 || quantity >= selectedSize.stock}
                >
                  +
                </button>
              </div>

              <button
                type="button"
                className={styles.addButton}
                disabled={!user}
                onClick={addToCart}
                title={!user ? 'Log in to add items to your cart' : undefined}
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
