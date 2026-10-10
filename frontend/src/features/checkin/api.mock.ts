import { ApiRequestError } from '../../api/client';
import { findUserByEmail, getCurrentMockUser } from '../auth/mockUsers';
import { findMockTicketByCodeOrToken, saveMockTicket } from '../tickets/mockTicketsStore';
import type { CheckinRequest, CheckinResponse } from './types';

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export const mockCheckinApi = {
  async scan({ token, code, event }: CheckinRequest): Promise<CheckinResponse> {
    await delay(300);

    if ((!token && !code) || (token && code)) {
      throw new ApiRequestError({ code: 'validation_error', message: 'Send exactly one of token or code.' });
    }

    const invalid: CheckinResponse = {
      result: 'invalid',
      ticket: null,
      holderName: null,
      membershipStatus: null,
      checkedInAt: null,
      checkedInBy: null,
    };

    const record = findMockTicketByCodeOrToken({ token, code });
    if (!record) return invalid;
    if (event !== undefined && record.eventId !== event) return invalid;

    const owner = findUserByEmail(record.ownerEmail);
    const ticketRef = { id: record.id, code: record.code, status: record.status, event: { id: record.eventId, title: record.eventTitle }, tier: { id: record.tierId, name: record.tierName } };

    if (record.status === 'cancelled') {
      return {
        result: 'cancelled',
        ticket: ticketRef,
        holderName: record.ownerName,
        membershipStatus: owner?.membershipStatus ?? null,
        checkedInAt: null,
        checkedInBy: null,
      };
    }

    if (record.status === 'checked_in') {
      return {
        result: 'already_checked_in',
        ticket: ticketRef,
        holderName: record.ownerName,
        membershipStatus: record.membershipStatusAtCheckin ?? null,
        checkedInAt: record.checkedInAt ?? null,
        checkedInBy: record.checkedInBy ?? null,
      };
    }

    // Valid, unused ticket — admit now.
    const scanner = getCurrentMockUser();
    const checkedInAt = new Date().toISOString();
    const checkedInBy = scanner?.name ?? 'Unknown staff';
    const membershipStatusNow = owner?.membershipStatus ?? 'none';

    saveMockTicket({
      ...record,
      status: 'checked_in',
      checkedInAt,
      checkedInBy,
      membershipStatusAtCheckin: membershipStatusNow,
    });

    return {
      result: 'ok',
      ticket: { ...ticketRef, status: 'checked_in' },
      holderName: record.ownerName,
      membershipStatus: membershipStatusNow,
      checkedInAt,
      checkedInBy,
    };
  },
};
