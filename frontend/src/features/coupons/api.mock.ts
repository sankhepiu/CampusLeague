import { ApiRequestError, type Paginated } from '../../api/client';
import { getCurrentMockUser } from '../auth/mockUsers';
import { mockCoupons, validateMockCoupon } from './mockCouponsStore';
import type { Coupon, CouponDraft, CouponValidateRequest, CouponValidateResponse } from './types';

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const COUPON_ADMIN_ROLES = ['president', 'treasurer'];

function requireCouponAdmin() {
  const user = getCurrentMockUser();
  if (!user) throw new ApiRequestError({ code: 'not_authenticated', message: 'No active session.' });
  if (!user.roles.some((r) => COUPON_ADMIN_ROLES.includes(r))) {
    throw new ApiRequestError({ code: 'permission_denied', message: 'Only the president or treasurer can manage coupons.' });
  }
}

export const mockCouponsApi = {
  async validate({ code, appliesTo, amount }: CouponValidateRequest): Promise<CouponValidateResponse> {
    await delay(300);
    const user = getCurrentMockUser();
    if (!user) throw new ApiRequestError({ code: 'not_authenticated', message: 'No active session.' });
    return validateMockCoupon(code, appliesTo, amount, user.email);
  },

  async list(): Promise<Paginated<Coupon>> {
    await delay(300);
    requireCouponAdmin();
    const results = mockCoupons.list();
    return { count: results.length, next: null, previous: null, results };
  },

  async create(draft: CouponDraft): Promise<Coupon> {
    await delay(350);
    requireCouponAdmin();
    return mockCoupons.create(draft);
  },

  async update(id: number, patch: Partial<CouponDraft>): Promise<Coupon> {
    await delay(350);
    requireCouponAdmin();
    return mockCoupons.update(id, patch);
  },

  async remove(id: number): Promise<void> {
    await delay(300);
    requireCouponAdmin();
    mockCoupons.remove(id);
  },
};
