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

/** POST /checkin with `member_token` (a member card, not a ticket). The
 * server records no check-in for these: it only reports membership. */
export type MemberScanResult = 'member_ok' | 'not_member' | 'invalid';

export interface MemberScanResponse {
  result: MemberScanResult;
  holder: { name: string; email: string } | null;
  membershipStatus: MembershipStatus | null;
}

/** What the scanner screen shows: a ticket check-in or a member-card lookup. */
export type ScanOutcome = ({ kind: 'ticket' } & CheckinResponse) | ({ kind: 'member' } & MemberScanResponse);
