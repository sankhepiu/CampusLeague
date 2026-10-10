import { request, type Paginated } from '../../api/client';
import type { ListMembersParams, MemberSummary } from './types';

/** GAP: speculative — GET /members has no contract entry. Field names assume
 * the same snake_case convention every other endpoint uses. */
interface WireMember {
  id: number;
  email: string;
  name: string;
  college_id: string;
  roles: MemberSummary['roles'];
  membership_status: MemberSummary['membershipStatus'];
}

function fromWire(m: WireMember): MemberSummary {
  return { id: m.id, email: m.email, name: m.name, collegeId: m.college_id, roles: m.roles, membershipStatus: m.membership_status };
}

export const realMembersApi = {
  async list({ status, search }: ListMembersParams): Promise<MemberSummary[]> {
    const page = await request<Paginated<WireMember>>('/members', { query: { status, search } });
    return page.results.map(fromWire);
  },
};
