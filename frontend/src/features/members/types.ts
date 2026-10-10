import type { MembershipStatus } from '../auth/types';
import type { Role } from '../../core/config/roles';

/** One row of GET /members, as documented in docs/API_CONTRACT.md. */
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
