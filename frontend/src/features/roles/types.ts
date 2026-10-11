import type { Role } from '../../core/config/roles';

export type InviteStatus = 'pending' | 'accepted' | 'declined' | 'revoked' | 'expired';

export interface RoleInvite {
  id: number;
  user: { id: number; name: string; email: string };
  role: Role;
  invitedBy: { id: number; name: string };
  status: InviteStatus;
  termStart: string; // YYYY-MM-DD
  termEnd: string;
  expiresAt: string;
  createdAt: string;
  respondedAt: string | null;
}

export interface RoleInviteDraft {
  user: number;
  role: Role;
  termStart?: string;
  termEnd?: string;
}

export interface ListInvitesParams {
  status?: InviteStatus;
}
