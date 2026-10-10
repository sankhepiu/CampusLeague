import { membersApi } from '../members/api';

export interface AssignableUser {
  id: number;
  name: string;
  email: string;
}

/** GAP: the contract has no endpoint that lists users — GET /members is the
 * same speculative, unconfirmed endpoint flagged back in Phase 1
 * (features/members/api.ts), not something docs/API_CONTRACT.md documents.
 * This just wraps it so the assignee picker has one call site to swap once
 * a real "list users" endpoint exists. Needs your teammate's sign-off. */
export async function listAssignableUsers(): Promise<AssignableUser[]> {
  const members = await membersApi.list({});
  return members.map((m) => ({ id: m.id, name: m.name, email: m.email }));
}
