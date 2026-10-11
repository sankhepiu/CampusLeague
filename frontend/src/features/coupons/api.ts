import { env } from '../../core/config/env';
import { mockCouponsApi } from './api.mock';
import { realCouponsApi } from './api.real';

/** Same typed surface regardless of mode — components never branch on env.useMockApi. */
export const couponsApi = env.useMockApi ? mockCouponsApi : realCouponsApi;

export type { Coupon, CouponAppliesTo, CouponDraft, CouponInvalidReason, CouponKind, CouponValidateAppliesTo, CouponValidateRequest, CouponValidateResponse } from './types';
