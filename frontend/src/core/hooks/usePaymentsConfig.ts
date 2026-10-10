import { useContext } from 'react';
import { PaymentsConfigContext } from '../providers/PaymentsConfigProvider';

export function usePaymentsConfig() {
  const ctx = useContext(PaymentsConfigContext);
  if (!ctx) throw new Error('usePaymentsConfig must be used within a PaymentsConfigProvider');
  return ctx;
}
