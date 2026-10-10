import { membersApi } from '../members/api';

export interface AssignableUser {
  id: number;
  name: string;
  email: string;
}

/** Everyone a task can be assigned to, from GET /members (documented in
 * docs/API_CONTRACT.md). Readable by president, treasurer, event manager
 * and volunteer coordinator, which covers everyone allowed to assign tasks. */
export async function listAssignableUsers(): Promise<AssignableUser[]> {
  const members = await membersApi.list({});
  return members.map((m) => ({ id: m.id, name: m.name, email: m.email }));
}
