import type { PixelIconName } from '../../components/PixelIcon';
import { FEATURE_ACCESS, type FeatureKey } from '../config/roles';

export interface NavItem {
  key: FeatureKey;
  path: string;
  label: string;
  icon: PixelIconName;
}

export const NAV_ITEMS: NavItem[] = [
  { key: 'membership', path: '/membership', label: 'Membership', icon: 'badge' },
  { key: 'events', path: '/events', label: 'Events', icon: 'trophy' },
  { key: 'tickets', path: '/tickets', label: 'Tickets', icon: 'chest' },
  { key: 'shop', path: '/shop', label: 'Shop', icon: 'chest' },
  { key: 'orders', path: '/orders', label: 'Orders', icon: 'chest' },
  { key: 'volunteering', path: '/volunteering', label: 'Volunteering', icon: 'trophy' },
  { key: 'announcements', path: '/announcements', label: 'Announcements', icon: 'badge' },
  { key: 'members', path: '/members', label: 'Members', icon: 'badge' },
  { key: 'checkin', path: '/checkin', label: 'Check-in', icon: 'badge' },
  { key: 'expenses', path: '/expenses', label: 'Expenses', icon: 'coin' },
  { key: 'expenseApproval', path: '/expenses/approvals', label: 'Approvals', icon: 'coin' },
  { key: 'finance', path: '/finance', label: 'Finance', icon: 'coin' },
  { key: 'insights', path: '/insights', label: 'Insights', icon: 'trophy' },
  { key: 'admin', path: '/admin', label: 'Admin', icon: 'badge' },
];

export function navItemsForRoles(roles: string[]): NavItem[] {
  return NAV_ITEMS.filter((item) => {
    const required = FEATURE_ACCESS[item.key];
    return required === null || required.some((r) => roles.includes(r));
  });
}
