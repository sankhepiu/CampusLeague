import { ApiRequestError } from '../../api/client';
import { findUserById, getCurrentMockUser } from '../auth/mockUsers';
import { addMockRoleAssignment, appendMockAudit, currentRoleHoldersCount, endMockRoleAssignment, findMockRoleAssignment } from '../admin/mockAdminStore';
import { ROLES } from '../../core/config/roles';
import type { InviteStatus, ListInvitesParams, RoleInvite, RoleInviteDraft } from './types';

interface MockInvite extends Omit<RoleInvite, 'status'> {
  status: InviteStatus;
}

const STORE_KEY = 'campusleague.mock.roleInvites';
const EXPIRY_MS = 72 * 60 * 60 * 1000;
const addYears = (iso: string, n: number) => {
  const d = new Date(iso);
  d.setFullYear(d.getFullYear() + n);
  return d.toISOString().slice(0, 10);
};
const today = () => new Date().toISOString().slice(0, 10);

function loadStore(): MockInvite[] {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) return JSON.parse(raw) as MockInvite[];
  } catch {
    /* storage unavailable or corrupt */
  }
  return [];
}

function saveStore(items: MockInvite[]): void {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(items));
  } catch {
    /* storage unavailable */
  }
}

/** A pending invite past its expiry reports as `expired` on read, without a
 * background job — matches the contract's "reported as expired" wording. */
function effectiveStatus(invite: MockInvite): InviteStatus {
  if (invite.status === 'pending' && Date.now() > new Date(invite.expiresAt).getTime()) return 'expired';
  return invite.status;
}

function toPublic(invite: MockInvite): RoleInvite {
  return { ...invite, status: effectiveStatus(invite) };
}

function requireUser() {
  const user = getCurrentMockUser();
  if (!user) throw new ApiRequestError({ code: 'not_authenticated', message: 'No active session.' });
  return user;
}

function requirePresident() {
  const user = requireUser();
  if (!user.roles.includes('president')) {
    throw new ApiRequestError({ code: 'permission_denied', message: 'Only the president can do this.' });
  }
  return user;
}

export const mockRoles = {
  listInvites(params: ListInvitesParams): RoleInvite[] {
    const user = requireUser();
    const isPresident = user.roles.includes('president');
    return loadStore()
      .filter((i) => isPresident || i.user.id === user.id)
      .map(toPublic)
      .filter((i) => !params.status || i.status === params.status)
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  },

  create(draft: RoleInviteDraft): RoleInvite {
    const actor = requirePresident();

    if (draft.user === actor.id) {
      throw new ApiRequestError({ code: 'self_assignment', message: 'You cannot nominate yourself.' });
    }
    if (!ROLES.includes(draft.role)) {
      throw new ApiRequestError({ code: 'validation_error', message: 'Not a recognised role.', field: 'role' });
    }
    const target = findUserById(draft.user);
    if (!target) {
      throw new ApiRequestError({ code: 'validation_error', message: 'No such user.', field: 'user', errors: [{ field: 'user', code: 'does_not_exist', message: 'No such user.' }] });
    }

    const termStart = draft.termStart ?? today();
    const termEnd = draft.termEnd ?? addYears(termStart, 1);
    if (termEnd < termStart) {
      throw new ApiRequestError({ code: 'validation_error', message: 'Term end cannot be before term start.', field: 'term_end', errors: [{ field: 'term_end', code: 'term_end_before_start', message: 'Term end cannot be before term start.' }] });
    }
    if (termEnd < today()) {
      throw new ApiRequestError({ code: 'validation_error', message: 'Term end is already in the past.', field: 'term_end', errors: [{ field: 'term_end', code: 'term_in_past', message: 'Term end is already in the past.' }] });
    }

    const store = loadStore();
    const hasPending = store.some((i) => i.user.id === draft.user && i.role === draft.role && effectiveStatus(i) === 'pending');
    if (hasPending) {
      throw new ApiRequestError({ code: 'invite_pending', message: 'This person already has a pending invite for that role.' });
    }
    if (target.roles.includes(draft.role)) {
      throw new ApiRequestError({ code: 'role_already_held', message: 'This person already holds that role.' });
    }

    const now = new Date();
    const invite: MockInvite = {
      id: store.reduce((max, i) => Math.max(max, i.id), 0) + 1,
      user: { id: target.id, name: target.name, email: target.email },
      role: draft.role,
      invitedBy: { id: actor.id, name: actor.name },
      status: 'pending',
      termStart,
      termEnd,
      expiresAt: new Date(now.getTime() + EXPIRY_MS).toISOString(),
      createdAt: now.toISOString(),
      respondedAt: null,
    };
    store.push(invite);
    saveStore(store);

    appendMockAudit({ actor: { id: actor.id, name: actor.name }, action: 'role.invited', objectType: 'RoleInvite', objectId: invite.id, before: null, after: { user: draft.user, role: draft.role } });

    return toPublic(invite);
  },

  respond(id: number, decision: 'accepted' | 'declined'): RoleInvite {
    const user = requireUser();
    const store = loadStore();
    const invite = store.find((i) => i.id === id);
    if (!invite || (!user.roles.includes('president') && invite.user.id !== user.id)) {
      throw new ApiRequestError({ code: 'not_found', message: 'No such invite.' });
    }
    if (invite.user.id !== user.id) {
      throw new ApiRequestError({ code: 'not_the_nominee', message: 'Only the nominee can answer this invite.' });
    }
    if (effectiveStatus(invite) !== 'pending') {
      throw new ApiRequestError({ code: 'invite_not_pending', message: 'This invite was already answered, revoked or has expired.' });
    }

    invite.status = decision;
    invite.respondedAt = new Date().toISOString();
    saveStore(store);

    if (decision === 'accepted') {
      addMockRoleAssignment(invite.user.id, invite.role, invite.termStart, invite.termEnd);
      appendMockAudit({ actor: { id: user.id, name: user.name }, action: 'role.assigned', objectType: 'RoleInvite', objectId: invite.id, before: null, after: { invite: invite.id, invitedBy: invite.invitedBy } });
    } else {
      appendMockAudit({ actor: { id: user.id, name: user.name }, action: 'role.invite_declined', objectType: 'RoleInvite', objectId: invite.id, before: { status: 'pending' }, after: { status: 'declined' } });
    }

    return toPublic(invite);
  },

  revoke(id: number): RoleInvite {
    const actor = requirePresident();
    const store = loadStore();
    const invite = store.find((i) => i.id === id);
    if (!invite) throw new ApiRequestError({ code: 'not_found', message: 'No such invite.' });
    if (effectiveStatus(invite) !== 'pending') {
      throw new ApiRequestError({ code: 'invite_not_pending', message: 'This invite was already answered or has expired.' });
    }
    invite.status = 'revoked';
    invite.respondedAt = new Date().toISOString();
    saveStore(store);
    appendMockAudit({ actor: { id: actor.id, name: actor.name }, action: 'role.invite_revoked', objectType: 'RoleInvite', objectId: invite.id, before: { status: 'pending' }, after: { status: 'revoked' } });
    return toPublic(invite);
  },

  endAssignment(assignmentId: number): { ended: boolean } {
    const actor = requirePresident();
    const assignment = findMockRoleAssignment(assignmentId);
    if (!assignment) throw new ApiRequestError({ code: 'not_found', message: 'No such role assignment.' });
    if (assignment.role === 'president' && currentRoleHoldersCount('president') <= 1) {
      throw new ApiRequestError({ code: 'last_president', message: 'The club must always keep at least one current president.' });
    }
    endMockRoleAssignment(assignment.user, assignment.role);
    appendMockAudit({ actor: { id: actor.id, name: actor.name }, action: 'role.ended', objectType: 'RoleAssignment', objectId: assignmentId, before: { user: assignment.user, role: assignment.role }, after: null });
    return { ended: true };
  },
};
