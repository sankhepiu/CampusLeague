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

/** POST /checkin with a group pass's QR content (or `token` recognised as
 * one — a scanner need not know ahead of time which kind of code it read). */
export type PassScanResult = 'admitted' | 'already_used' | 'wrong_event' | 'invalid';

export interface PassScanResponse {
  result: PassScanResult;
  passId: number | null;
  admitted: number | null;
  admittedNow: number | null;
  total: number | null;
  remaining: number | null;
  holder: { name: string } | null;
  membershipStatus: MembershipStatus | null;
  event: { id: number; title: string } | null;
  tier: { id: number; name: string } | null;
}

export interface CheckinRequest {
  token?: string;
  code?: string;
  /** Group passes only — how many people to admit with this scan, 1 to 10.
   * Ignored for tickets and member cards. */
  count?: number;
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

/** What the scanner screen shows: a ticket check-in, a group-pass scan, or a
 * member-card lookup. */
export type ScanOutcome = ({ kind: 'ticket' } & CheckinResponse) | ({ kind: 'pass' } & PassScanResponse) | ({ kind: 'member' } & MemberScanResponse);
