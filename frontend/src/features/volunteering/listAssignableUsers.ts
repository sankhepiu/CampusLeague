import { membersApi } from '../members/api';

export interface AssignableUser {
  id: number;
  name: string;
  email: string;
}

/** Everyone a task can be assigned to, from GET /members. The contract docs
 * still list this as president/treasurer/event-manager only, but the
 * backend now also allows volunteer_coordinator — confirmed directly by the
 * brief that added task assignment, ahead of the docs catching up. */
export async function listAssignableUsers(): Promise<AssignableUser[]> {
  const members = await membersApi.list({});
  return members.map((m) => ({ id: m.id, name: m.name, email: m.email }));
}
