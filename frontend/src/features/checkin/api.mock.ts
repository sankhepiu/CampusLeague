import { ApiRequestError } from '../../api/client';
import type { MembershipStatus } from '../auth/types';
import { findUserByEmail, findUserById, getCurrentMockUser } from '../auth/mockUsers';
import { MOCK_MEMBER_TOKEN_PREFIX } from '../membership/api.mock';
import { admitMockPass, findMockPassTicketsByToken, findMockTicketByCodeOrToken, saveMockTicket, type MockTicketRecord } from '../tickets/mockTicketsStore';
import type { CheckinRequest, CheckinResponse, MemberScanResponse, PassScanResponse, ScanOutcome } from './types';

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function handlePassScan(tickets: MockTicketRecord[], count: number, event: number | undefined): PassScanResponse {
  const first = tickets[0];

  if (event !== undefined && first.eventId !== event) {
    return { result: 'wrong_event', passId: null, admitted: null, admittedNow: null, total: null, remaining: null, holder: null, membershipStatus: null, event: null, tier: null };
  }

  const owner = findUserByEmail(first.ownerEmail);
  const membershipStatus: MembershipStatus = owner?.membershipStatus ?? 'none';
  const eventRef = { id: first.eventId, title: first.eventTitle };
  const tierRef = { id: first.tierId, name: first.tierName };
  const holder = { name: first.ownerName };

  const notCancelled = tickets.filter((t) => t.status !== 'cancelled');
  const total = notCancelled.length;
  const admittedBefore = notCancelled.filter((t) => t.status === 'checked_in').length;
  const remainingBefore = total - admittedBefore;

  if (remainingBefore === 0) {
    return { result: 'already_used', passId: first.passId, admitted: total, admittedNow: 0, total, remaining: 0, holder, membershipStatus, event: eventRef, tier: tierRef };
  }

  if (count > remainingBefore) {
    throw new ApiRequestError({
      code: 'validation_error',
      message: `Only ${remainingBefore} left on this pass.`,
      field: 'count',
      errors: [{ field: 'count', code: 'exceeds_remaining', message: `Only ${remainingBefore} left on this pass.` }],
    });
  }

  const scanner = getCurrentMockUser();
  const admittedNow = admitMockPass(first.passId, count, scanner?.name ?? 'Unknown staff', membershipStatus).length;
  const admitted = admittedBefore + admittedNow;
  return { result: 'admitted', passId: first.passId, admitted, admittedNow, total, remaining: total - admitted, holder, membershipStatus, event: eventRef, tier: tierRef };
}

export const mockCheckinApi = {
  async scan({ token, code, count, event }: CheckinRequest): Promise<ScanOutcome> {
    await delay(300);

    if ((!token && !code) || (token && code)) {
      throw new ApiRequestError({ code: 'validation_error', message: 'Send exactly one of token or code.' });
    }

    if (token) {
      const passTickets = findMockPassTicketsByToken(token);
      if (passTickets) return { kind: 'pass', ...handlePassScan(passTickets, count ?? 1, event) };
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
    if (!record) return { kind: 'ticket', ...invalid };
    if (event !== undefined && record.eventId !== event) return { kind: 'ticket', ...invalid };

    const owner = findUserByEmail(record.ownerEmail);
    const ticketRef = { id: record.id, code: record.code, status: record.status, event: { id: record.eventId, title: record.eventTitle }, tier: { id: record.tierId, name: record.tierName } };

    if (record.status === 'cancelled') {
      return {
        kind: 'ticket',
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
        kind: 'ticket',
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
      kind: 'ticket',
      result: 'ok',
      ticket: { ...ticketRef, status: 'checked_in' },
      holderName: record.ownerName,
      membershipStatus: membershipStatusNow,
      checkedInAt,
      checkedInBy,
    };
  },

  async scanMember(memberToken: string): Promise<MemberScanResponse> {
    await delay(300);
    const invalid: MemberScanResponse = { result: 'invalid', holder: null, membershipStatus: null };
    if (!memberToken.startsWith(MOCK_MEMBER_TOKEN_PREFIX)) return invalid;
    const id = Number(memberToken.slice(MOCK_MEMBER_TOKEN_PREFIX.length));
    const member = Number.isInteger(id) ? findUserById(id) : undefined;
    if (!member) return invalid;
    return {
      result: member.membershipStatus === 'active' ? 'member_ok' : 'not_member',
      holder: { name: member.name, email: member.email },
      membershipStatus: member.membershipStatus,
    };
  },
};
