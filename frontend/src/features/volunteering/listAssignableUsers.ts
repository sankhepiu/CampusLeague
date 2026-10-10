import { membersApi } from '../members/api';

export interface AssignableUser {
  id: number;
  name: string;
  email: string;
}

/** Everyone a task can be assigned to, from GET /members (documented in
 * docs/API_CONTRACT.md). Note that endpoint is limited to president,
 * treasurer and event manager, so a volunteer coordinator who is none of
 * those gets a 403 here. */
export async function listAssignableUsers(): Promise<AssignableUser[]> {
  const members = await membersApi.list({});
  return members.map((m) => ({ id: m.id, name: m.name, email: m.email }));
}
