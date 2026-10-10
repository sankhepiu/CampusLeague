import { useContext } from 'react';
import { CartContext } from '../providers/CartProvider';

export function useCart() {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error('useCart must be used within a CartProvider');
  return ctx;
}
