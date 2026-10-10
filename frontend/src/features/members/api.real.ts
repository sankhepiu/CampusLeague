import { request, type Paginated } from '../../api/client';
import type { ListMembersParams, MemberSummary } from './types';

/** GET /members, as documented in docs/API_CONTRACT.md. */
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
  /** Every matching member, not just the first page. The endpoint returns
   * 20 per page; callers here (the members table, the role and task
   * pickers) need the whole list, so this follows `next` to the end. Fine
   * for a club-sized list; MAX_PAGES stops a runaway loop. */
  async list({ status, search }: ListMembersParams): Promise<MemberSummary[]> {
    const MAX_PAGES = 50;
    const members: MemberSummary[] = [];
    for (let pageNumber = 1; pageNumber <= MAX_PAGES; pageNumber += 1) {
      const page = await request<Paginated<WireMember>>('/members', { query: { status, search, page: pageNumber } });
      members.push(...page.results.map(fromWire));
      if (!page.next) break;
    }
    return members;
  },
};
