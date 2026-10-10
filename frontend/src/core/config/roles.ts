export const ROLES = ['member', 'organizer', 'admin'] as const;

export type Role = (typeof ROLES)[number];

export const ROLE_LABELS: Record<Role, string> = {
  member: 'Member',
  organizer: 'Organizer',
  admin: 'Admin',
};

/** Which roles may access each feature area. Used by route guards and home nav. */
export const FEATURE_ACCESS = {
  membership: ['member', 'organizer', 'admin'],
  events: ['member', 'organizer', 'admin'],
  tickets: ['member', 'organizer', 'admin'],
  shop: ['member', 'organizer', 'admin'],
  orders: ['member', 'organizer', 'admin'],
  volunteering: ['member', 'organizer', 'admin'],
  announcements: ['organizer', 'admin'],
  checkin: ['organizer', 'admin'],
  expenses: ['organizer', 'admin'],
  finance: ['admin'],
  insights: ['admin'],
  admin: ['admin'],
} as const satisfies Record<string, Role[]>;

export type FeatureKey = keyof typeof FEATURE_ACCESS;
