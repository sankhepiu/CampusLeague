import type { MembershipStatus } from '../auth/types';
import type { Role } from '../../core/config/roles';

/** GAP: GET /members (R6, staff members list) is not documented anywhere in
 * docs/API_CONTRACT.md — only auth and membership endpoints are. This shape
 * is an assumption, built from the contract's own "User object" fields plus
 * the obvious status/search query params a list like this needs. Needs your
 * teammate's sign-off before the real endpoint lands. */
export interface MemberSummary {
  id: number;
  email: string;
  name: string;
  collegeId: string;
  roles: Role[];
  membershipStatus: MembershipStatus;
}

export interface ListMembersParams {
  status?: MembershipStatus;
  search?: string;
}
