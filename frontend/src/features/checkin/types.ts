import type { MembershipStatus } from '../auth/types';
import type { TicketStatus } from '../tickets/types';

export type CheckinResult = 'ok' | 'already_checked_in' | 'cancelled' | 'invalid';

export interface CheckinTicketRef {
  id: number;
  code: string;
  status: TicketStatus;
  event: { id: number; title: string };
  tier: { id: number; name: string };
}

export interface CheckinResponse {
  result: CheckinResult;
  ticket: CheckinTicketRef | null;
  holderName: string | null;
  membershipStatus: MembershipStatus | null;
  checkedInAt: string | null;
  checkedInBy: string | null;
}

export interface CheckinRequest {
  token?: string;
  code?: string;
  event?: number;
}
