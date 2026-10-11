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
  // Announcements archive (GET /announcements) is public per the contract —
  // this entry only governs the nav link for signed-in users; the routes
  // themselves live in AppRoutes' public group, same as events.
  announcements: null,
  tickets: null,
  shop: null,
  orders: null,
  volunteering: null,
  members: ['president', 'treasurer', 'event_manager'],
  // Check-in reveals membership status to whoever is scanning, so it was
  // deliberately narrow — the contract still says "President or event
  // manager only," but the backend team has confirmed volunteer_coordinator
  // is now allowed too (they often work the door at events).
  checkin: ['president', 'event_manager', 'volunteer_coordinator'],
  eventAdmin: ['president', 'event_manager'],
  shopAdmin: ['president', 'treasurer', 'event_manager'],
  couponAdmin: ['president', 'treasurer'],
  roleAdmin: ['president'],
  announcementCompose: ['president', 'event_manager', 'volunteer_coordinator'],
  volunteerAdmin: ['president', 'volunteer_coordinator'],
  // Submitting/viewing your own reimbursement requests is open to anyone —
  // only the approval queue below is staff-gated. The old `expenses: [...]`
  // guess predated the contract; expense SUBMISSION was never staff-only.
  expenses: null,
  expenseApproval: ['president', 'treasurer'],
  finance: ['president', 'treasurer'],
  insights: ['president', 'treasurer', 'event_manager'],
  admin: ['president'],
} as const satisfies Record<string, Role[] | null>;

export type FeatureKey = keyof typeof FEATURE_ACCESS;
