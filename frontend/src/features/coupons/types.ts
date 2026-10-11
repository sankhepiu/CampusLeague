export type CouponKind = 'percent' | 'flat';
export type CouponAppliesTo = 'all' | 'merch' | 'tickets' | 'membership';
export type CouponValidateAppliesTo = 'merch' | 'tickets' | 'membership';

export interface Coupon {
  id: number;
  code: string;
  kind: CouponKind;
  value: number; // percent: 1-100; flat: paise
  minOrder: number; // paise
  maxDiscount: number | null; // paise
  validFrom: string | null;
  validTo: string | null;
  usageLimit: number | null;
  perUserLimit: number;
  appliesTo: CouponAppliesTo;
  active: boolean;
  usedCount: number;
  createdAt: string;
}

export interface CouponDraft {
  code: string;
  kind: CouponKind;
  value: number;
  minOrder?: number;
  maxDiscount?: number | null;
  validFrom?: string | null;
  validTo?: string | null;
  usageLimit?: number | null;
  perUserLimit?: number;
  appliesTo?: CouponAppliesTo;
  active?: boolean;
}

export type CouponInvalidReason =
  | 'not_found'
  | 'inactive'
  | 'not_started'
  | 'expired'
  | 'not_applicable'
  | 'min_order_not_met'
  | 'usage_limit_reached'
  | 'already_used'
  | 'no_discount';

export interface CouponValidateRequest {
  code: string;
  appliesTo: CouponValidateAppliesTo;
  amount: number; // paise
}

export interface CouponValidateResponse {
  valid: boolean;
  discount: number; // paise
  finalAmount: number; // paise
  reason: CouponInvalidReason | null;
  message: string | null;
}
