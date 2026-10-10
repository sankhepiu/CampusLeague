import type { PixelIconName } from '../../components/PixelIcon';
import type { FeatureKey } from '../config/roles';
import type { Role } from '../config/roles';

export interface DashboardTool {
  key: string;
  path: string;
  label: string;
  icon: PixelIconName;
  accentKey: FeatureKey;
}

/** Each role's own tools, shown first on their dashboard, ahead of "My
 * account". Browsing-only areas (Events, Shop, Volunteering, Announcements)
 * are deliberately left off a staff dashboard — they're still one click away
 * in the top nav — so the dashboard stays focused on what that role is
 * actually there to do. */
export const ROLE_TOOLS: Partial<Record<Role, DashboardTool[]>> = {
  president: [
    { key: 'members', path: '/members', label: 'Members', icon: 'badge', accentKey: 'members' },
    { key: 'admin', path: '/admin', label: 'Admin', icon: 'badge', accentKey: 'admin' },
    { key: 'finance', path: '/finance', label: 'Finance', icon: 'coin', accentKey: 'finance' },
    { key: 'expenseApproval', path: '/expenses/approvals', label: 'Approvals', icon: 'coin', accentKey: 'expenseApproval' },
    { key: 'checkin', path: '/checkin', label: 'Check-in', icon: 'badge', accentKey: 'checkin' },
    { key: 'insights', path: '/insights', label: 'Insights', icon: 'trophy', accentKey: 'insights' },
  ],
  treasurer: [
    { key: 'expenseApproval', path: '/expenses/approvals', label: 'Approvals', icon: 'coin', accentKey: 'expenseApproval' },
    { key: 'finance', path: '/finance', label: 'Finance', icon: 'coin', accentKey: 'finance' },
    { key: 'ledger', path: '/finance/ledger', label: 'Ledger', icon: 'coin', accentKey: 'finance' },
    { key: 'insights', path: '/insights', label: 'Insights', icon: 'trophy', accentKey: 'insights' },
  ],
  event_manager: [
    { key: 'eventAdmin', path: '/events', label: 'Event Admin', icon: 'trophy', accentKey: 'eventAdmin' },
    { key: 'checkin', path: '/checkin', label: 'Check-in', icon: 'badge', accentKey: 'checkin' },
    { key: 'insights', path: '/insights', label: 'Insights', icon: 'trophy', accentKey: 'insights' },
  ],
  volunteer_coordinator: [
    { key: 'volunteerAdmin', path: '/volunteering', label: 'Fundraiser Admin', icon: 'trophy', accentKey: 'volunteerAdmin' },
    { key: 'checkin', path: '/checkin', label: 'Check-in', icon: 'badge', accentKey: 'checkin' },
  ],
};

/** Every signed-in user's own account tools — shown after role tools for
 * staff, or as the whole dashboard for a plain member (handled in
 * HomePage, which keeps that case on the original full nav grid instead). */
export const MY_ACCOUNT_TOOLS: DashboardTool[] = [
  { key: 'membership', path: '/membership', label: 'Membership', icon: 'badge', accentKey: 'membership' },
  { key: 'tickets', path: '/tickets', label: 'Tickets', icon: 'chest', accentKey: 'tickets' },
  { key: 'orders', path: '/orders', label: 'Orders', icon: 'chest', accentKey: 'orders' },
  { key: 'expenses', path: '/expenses', label: 'Expenses', icon: 'coin', accentKey: 'expenses' },
];

/** Union of every current role's tools, deduped by key, in a stable order. */
export function toolsForRoles(roles: Role[]): DashboardTool[] {
  const seen = new Set<string>();
  const tools: DashboardTool[] = [];
  for (const role of roles) {
    for (const tool of ROLE_TOOLS[role] ?? []) {
      if (seen.has(tool.key)) continue;
      seen.add(tool.key);
      tools.push(tool);
    }
  }
  return tools;
}
