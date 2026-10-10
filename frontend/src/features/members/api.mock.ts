import { listAllUsers } from '../auth/mockUsers';
import type { ListMembersParams, MemberSummary } from './types';

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export const mockMembersApi = {
  async list({ status, search }: ListMembersParams): Promise<MemberSummary[]> {
    await delay(350);
    const term = search?.trim().toLowerCase();
    return listAllUsers()
      .filter((u) => !status || u.membershipStatus === status)
      .filter((u) => !term || u.name.toLowerCase().includes(term) || u.email.toLowerCase().includes(term) || u.collegeId.toLowerCase().includes(term))
      .map((u) => ({ id: u.id, email: u.email, name: u.name, collegeId: u.collegeId, roles: u.roles, membershipStatus: u.membershipStatus }))
      .sort((a, b) => a.name.localeCompare(b.name));
  },
};
