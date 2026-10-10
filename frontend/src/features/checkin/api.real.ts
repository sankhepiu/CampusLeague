import { request } from '../../api/client';
import type { CheckinRequest, CheckinResponse, CheckinResult, CheckinTicketRef } from './types';
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

export const realCheckinApi = {
  async scan({ token, code, event }: CheckinRequest): Promise<CheckinResponse> {
    const result = await request<WireCheckinResponse>('/checkin', {
      method: 'POST',
      body: { ...(token ? { token } : {}), ...(code ? { code } : {}), ...(event !== undefined ? { event } : {}) },
    });
    return {
      result: result.result,
      ticket: result.ticket,
      holderName: result.holder_name,
      membershipStatus: result.membership_status,
      checkedInAt: result.checked_in_at,
      checkedInBy: result.checked_in_by,
    };
  },
};
