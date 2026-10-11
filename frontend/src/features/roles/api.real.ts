import { request, type Paginated } from '../../api/client';
import type { ListInvitesParams, RoleInvite, RoleInviteDraft } from './types';

interface WireRoleInvite {
  id: number;
  user: { id: number; name: string; email: string };
  role: RoleInvite['role'];
  invited_by: { id: number; name: string };
  status: RoleInvite['status'];
  term_start: string;
  term_end: string;
  expires_at: string;
  created_at: string;
  responded_at: string | null;
}

function fromWireInvite(i: WireRoleInvite): RoleInvite {
  return {
    id: i.id,
    user: i.user,
    role: i.role,
    invitedBy: i.invited_by,
    status: i.status,
    termStart: i.term_start,
    termEnd: i.term_end,
    expiresAt: i.expires_at,
    createdAt: i.created_at,
    respondedAt: i.responded_at,
  };
}

export const realRolesApi = {
  async create(draft: RoleInviteDraft): Promise<RoleInvite> {
    return fromWireInvite(
      await request<WireRoleInvite>('/roles', {
        method: 'POST',
        body: {
          user: draft.user,
          role: draft.role,
          ...(draft.termStart !== undefined ? { term_start: draft.termStart } : {}),
          ...(draft.termEnd !== undefined ? { term_end: draft.termEnd } : {}),
        },
      }),
    );
  },

  async listInvites(params: ListInvitesParams = {}): Promise<Paginated<RoleInvite>> {
    const result = await request<Paginated<WireRoleInvite>>('/roles/invites', { query: { status: params.status } });
    return { ...result, results: result.results.map(fromWireInvite) };
  },

  async accept(id: number): Promise<RoleInvite> {
    return fromWireInvite(await request<WireRoleInvite>(`/roles/invites/${id}/accept`, { method: 'POST' }));
  },

  async decline(id: number): Promise<RoleInvite> {
    return fromWireInvite(await request<WireRoleInvite>(`/roles/invites/${id}/decline`, { method: 'POST' }));
  },

  async revoke(id: number): Promise<RoleInvite> {
    return fromWireInvite(await request<WireRoleInvite>(`/roles/invites/${id}/revoke`, { method: 'POST' }));
  },

  async endAssignment(assignmentId: number): Promise<{ ended: boolean }> {
    const r = await request<{ ended: boolean }>(`/roles/${assignmentId}/end`, { method: 'POST' });
    return { ended: r.ended };
  },
};
