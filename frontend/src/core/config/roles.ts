/** Committee roles, exactly as docs/API_CONTRACT.md defines them. An ordinary
 * signed-up user has `roles: []` — being a paid-up member is tracked
 * separately via `membershipStatus`, never via the `member` role. See the
 * "User object" section of the contract. */
export const ROLES = ['president', 'treasurer', 'event_manager', 'volunteer_coordinator', 'member'] as const;

export type Role = (typeof ROLES)[number];

export const ROLE_LABELS: Record<Role, string> = {
  president: 'President',
  treasurer: 'Treasurer',
  event_manager: 'Event Manager',
  volunteer_coordinator: 'Volunteer Coordinator',
  member: 'Member',
};

/** Which roles may access each feature area, used by route guards and home
 * nav. `null` means "any authenticated user" — most member-facing areas
 * aren't gated by committee role at all, only by being logged in. */
export const FEATURE_ACCESS = {
  membership: null,
  events: null,
  tickets: null,
  shop: null,
  orders: null,
  volunteering: null,
  announcements: null,
  members: ['president', 'treasurer', 'event_manager'],
  // Check-in reveals membership status to whoever is scanning, so it's
  // deliberately narrower than most staff areas — contract is explicit:
  // "President or event manager only."
  checkin: ['president', 'event_manager'],
  eventAdmin: ['president', 'event_manager'],
  expenses: ['president', 'treasurer', 'volunteer_coordinator'],
  finance: ['president', 'treasurer'],
  insights: ['president', 'treasurer', 'event_manager'],
  admin: ['president'],
} as const satisfies Record<string, Role[] | null>;

export type FeatureKey = keyof typeof FEATURE_ACCESS;
