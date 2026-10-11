import { createContext, useCallback, useMemo, type ReactNode } from 'react';
import { useLocalStorageState } from '../hooks/useLocalStorageState';
import { LIMIT_REACHED_MESSAGE, MAX_PER_ITEM } from '../../features/shop/limits';

export interface CartItem {
  productSizeId: number;
  productId: number;
  productName: string;
  productImage: string | null;
  sizeLabel: string;
  /** Snapshots of price at add-time, for an estimated order-summary
   * breakdown only — the authoritative total always comes from the
   * server's order response. */
  unitPriceEstimate: number;
  unitBasePriceEstimate: number;
  /** Price after the sale discount but before any member discount — lets the
   * cart show "sale" and "member" as two separate summary lines. */
  unitSalePriceEstimate: number;
  quantity: number;
}

const MAX_LINES = 20;
const MAX_QTY = MAX_PER_ITEM;

interface CartContextValue {
  items: CartItem[];
  /** `added` is how many actually went in. When that is fewer than asked
   * for (the per-item limit), `reason` says so: an add is never silently
   * dropped or cut short. */
  addItem: (item: Omit<CartItem, 'quantity'>, quantity: number) => { ok: boolean; added: number; reason?: string };
  updateQuantity: (productSizeId: number, quantity: number) => void;
  removeItem: (productSizeId: number) => void;
  clear: () => void;
  estimatedSubtotal: number;
}

export const CartContext = createContext<CartContextValue | null>(null);

export function CartProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useLocalStorageState<CartItem[]>('campusleague.cart', []);

  const addItem = useCallback(
    (item: Omit<CartItem, 'quantity'>, quantity: number): { ok: boolean; added: number; reason?: string } => {
      // Decided from the cart as it is now, before the update is queued, so
      // the caller gets the real outcome to show.
      const existing = items.find((i) => i.productSizeId === item.productSizeId);
      const inCart = existing?.quantity ?? 0;
      if (!existing && items.length >= MAX_LINES) {
        return { ok: false, added: 0, reason: `Your cart can hold at most ${MAX_LINES} different sizes.` };
      }
      // The limit is on the total: what is in the cart plus what is added.
      const added = Math.max(0, Math.min(quantity, MAX_QTY - inCart));
      if (added === 0) return { ok: false, added: 0, reason: LIMIT_REACHED_MESSAGE };

      setItems((prev) => {
        const current = prev.find((i) => i.productSizeId === item.productSizeId);
        if (current) {
          const nextQty = Math.min(MAX_QTY, current.quantity + added);
          return prev.map((i) => (i.productSizeId === item.productSizeId ? { ...i, quantity: nextQty } : i));
        }
        return [...prev, { ...item, quantity: added }];
      });
      return added < quantity
        ? { ok: true, added, reason: `Only ${added} added: the limit is ${MAX_QTY} per item and you already had ${inCart} in your cart.` }
        : { ok: true, added };
    },
    [items, setItems],
  );

  const updateQuantity = useCallback(
    (productSizeId: number, quantity: number) => {
      setItems((prev) =>
        quantity <= 0
          ? prev.filter((i) => i.productSizeId !== productSizeId)
          : prev.map((i) => (i.productSizeId === productSizeId ? { ...i, quantity: Math.min(MAX_QTY, quantity) } : i)),
      );
    },
    [setItems],
  );

  const removeItem = useCallback((productSizeId: number) => setItems((prev) => prev.filter((i) => i.productSizeId !== productSizeId)), [setItems]);
  const clear = useCallback(() => setItems([]), [setItems]);

  const estimatedSubtotal = useMemo(() => items.reduce((sum, i) => sum + i.unitPriceEstimate * i.quantity, 0), [items]);

  const value = useMemo<CartContextValue>(
    () => ({ items, addItem, updateQuantity, removeItem, clear, estimatedSubtotal }),
    [items, addItem, updateQuantity, removeItem, clear, estimatedSubtotal],
  );

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}
