import { request } from '../../api/client';
import type { CheckinRequest, CheckinResult, CheckinTicketRef, MemberScanResponse, MemberScanResult, PassScanResult, ScanOutcome } from './types';
import type { MembershipStatus } from '../auth/types';

interface WireCheckinResponse {
  result: CheckinResult;
  ticket: {
    id: number;
    code: string;
    status: CheckinTicketRef['status'];
    event: { id: number; title: string };
    tier: { id: number; name: string };
  } | null;
  holder_name: string | null;
  membership_status: MembershipStatus | null;
  checked_in_at: string | null;
  checked_in_by: string | null;
}

interface WirePassScanResponse {
  result: PassScanResult;
  pass_id: number | null;
  admitted: number | null;
  admitted_now: number | null;
  total: number | null;
  remaining: number | null;
  holder: { name: string } | null;
  membership_status: MembershipStatus | null;
  event: { id: number; title: string } | null;
  tier: { id: number; name: string } | null;
}

export const realCheckinApi = {
  async scan({ token, code, count, event }: CheckinRequest): Promise<ScanOutcome> {
    const result = await request<WireCheckinResponse | WirePassScanResponse>('/checkin', {
      method: 'POST',
      body: {
        ...(token ? { token } : {}),
        ...(code ? { code } : {}),
        ...(count !== undefined ? { count } : {}),
        ...(event !== undefined ? { event } : {}),
      },
    });

    if ('pass_id' in result) {
      return {
        kind: 'pass',
        result: result.result,
        passId: result.pass_id,
        admitted: result.admitted,
        admittedNow: result.admitted_now,
        total: result.total,
        remaining: result.remaining,
        holder: result.holder,
        membershipStatus: result.membership_status,
        event: result.event,
        tier: result.tier,
      };
    }

    return {
      kind: 'ticket',
      result: result.result,
      ticket: result.ticket,
      holderName: result.holder_name,
      membershipStatus: result.membership_status,
      checkedInAt: result.checked_in_at,
      checkedInBy: result.checked_in_by,
    };
  },

  /** Looks up a member card. Same endpoint, different body and a smaller
   * response; nothing is recorded, so it is safe to call repeatedly. */
  async scanMember(memberToken: string): Promise<MemberScanResponse> {
    const result = await request<{
      result: MemberScanResult;
      holder: { name: string; email: string } | null;
      membership_status: MembershipStatus | null;
    }>('/checkin', { method: 'POST', body: { member_token: memberToken } });
    return { result: result.result, holder: result.holder, membershipStatus: result.membership_status };
  },
};
