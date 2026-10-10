import { useContext } from 'react';
import { OptionsContext } from '../providers/OptionsProvider';

export function useOptions() {
  const ctx = useContext(OptionsContext);
  if (!ctx) throw new Error('useOptions must be used within an OptionsProvider');
  return ctx;
}
