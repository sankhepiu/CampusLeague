import { Link } from 'react-router-dom';
import { useCart } from '../../core/hooks/useCart';
import styles from './ViewCartButton.module.scss';

/** Sticky "View Cart (n) →" shown once anything is in the cart. It remounts
 * (and so plays its short highlight) whenever the item count changes. */
export function ViewCartButton() {
  const { items } = useCart();
  const count = items.reduce((sum, i) => sum + i.quantity, 0);
  if (count === 0) return null;
  return (
    <Link key={count} to="/shop/cart" className={styles.button}>
      View Cart ({count}) →
    </Link>
  );
}
