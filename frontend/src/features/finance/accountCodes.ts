import type { LedgerAccount } from './types';

/** All nine account codes, confirmed against the real backend (4300 is now
 * also named directly in the contract; 5100/5200 were confirmed by the
 * backend team). Shared (not mock-only) since both the mock ledger engine
 * and the Ledger page's account filter need the same list, and this has to
 * work the same way against the real API too. */
export const ACCOUNTS: Record<string, LedgerAccount> = {
  '1000': { code: '1000', name: 'Cash', type: 'asset' },
  '2000': { code: '2000', name: 'Reimbursements payable', type: 'liability' },
  '4000': { code: '4000', name: 'Membership dues revenue', type: 'revenue' },
  '4100': { code: '4100', name: 'Ticket revenue', type: 'revenue' },
  '4200': { code: '4200', name: 'Merchandise revenue', type: 'revenue' },
  '4300': { code: '4300', name: 'Fundraiser revenue', type: 'revenue' },
  '5000': { code: '5000', name: 'Event expenses', type: 'expense' },
  '5100': { code: '5100', name: 'Fundraiser expenses', type: 'expense' },
  '5200': { code: '5200', name: 'General expenses', type: 'expense' },
};

export const ACCOUNT_LIST: LedgerAccount[] = Object.values(ACCOUNTS);
