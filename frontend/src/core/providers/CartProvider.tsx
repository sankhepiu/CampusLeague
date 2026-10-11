import { createContext, useCallback, useMemo, type ReactNode } from 'react';
import { useLocalStorageState } from '../hooks/useLocalStorageState';

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
const MAX_QTY = 10;

interface CartContextValue {
  items: CartItem[];
  addItem: (item: Omit<CartItem, 'quantity'>, quantity: number) => { ok: boolean; reason?: string };
  updateQuantity: (productSizeId: number, quantity: number) => void;
  removeItem: (productSizeId: number) => void;
  clear: () => void;
  estimatedSubtotal: number;
}

export const CartContext = createContext<CartContextValue | null>(null);

export function CartProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useLocalStorageState<CartItem[]>('campusleague.cart', []);

  const addItem = useCallback(
    (item: Omit<CartItem, 'quantity'>, quantity: number): { ok: boolean; reason?: string } => {
      let result: { ok: boolean; reason?: string } = { ok: true };
      setItems((prev) => {
        const existing = prev.find((i) => i.productSizeId === item.productSizeId);
        if (existing) {
          const nextQty = Math.min(MAX_QTY, existing.quantity + quantity);
          return prev.map((i) => (i.productSizeId === item.productSizeId ? { ...i, quantity: nextQty } : i));
        }
        if (prev.length >= MAX_LINES) {
          result = { ok: false, reason: `Your cart can hold at most ${MAX_LINES} different sizes.` };
          return prev;
        }
        return [...prev, { ...item, quantity: Math.min(MAX_QTY, quantity) }];
      });
      return result;
    },
    [setItems],
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
