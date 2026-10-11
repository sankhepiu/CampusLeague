import type { Paginated } from '../../api/client';
import { mockRoles } from './mockRolesStore';
import type { ListInvitesParams, RoleInvite, RoleInviteDraft } from './types';

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export const mockRolesApi = {
  async create(draft: RoleInviteDraft): Promise<RoleInvite> {
    await delay(350);
    return mockRoles.create(draft);
  },

  async listInvites(params: ListInvitesParams = {}): Promise<Paginated<RoleInvite>> {
    await delay(300);
    const results = mockRoles.listInvites(params);
    return { count: results.length, next: null, previous: null, results };
  },

  async accept(id: number): Promise<RoleInvite> {
    await delay(350);
    return mockRoles.respond(id, 'accepted');
  },

  async decline(id: number): Promise<RoleInvite> {
    await delay(300);
    return mockRoles.respond(id, 'declined');
  },

  async revoke(id: number): Promise<RoleInvite> {
    await delay(300);
    return mockRoles.revoke(id);
  },

  async endAssignment(assignmentId: number): Promise<{ ended: boolean }> {
    await delay(350);
    return mockRoles.endAssignment(assignmentId);
  },
};
