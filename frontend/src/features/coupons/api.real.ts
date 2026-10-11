import { request, type Paginated } from '../../api/client';
import type { Coupon, CouponDraft, CouponValidateRequest, CouponValidateResponse } from './types';

interface WireCoupon {
  id: number;
  code: string;
  kind: Coupon['kind'];
  value: number;
  min_order: number;
  max_discount: number | null;
  valid_from: string | null;
  valid_to: string | null;
  usage_limit: number | null;
  per_user_limit: number;
  applies_to: Coupon['appliesTo'];
  active: boolean;
  used_count: number;
  created_at: string;
}

interface WireCouponValidateResponse {
  valid: boolean;
  discount: number;
  final_amount: number;
  reason: CouponValidateResponse['reason'];
  message: string | null;
}

function fromWireCoupon(c: WireCoupon): Coupon {
  return {
    id: c.id,
    code: c.code,
    kind: c.kind,
    value: c.value,
    minOrder: c.min_order,
    maxDiscount: c.max_discount,
    validFrom: c.valid_from,
    validTo: c.valid_to,
    usageLimit: c.usage_limit,
    perUserLimit: c.per_user_limit,
    appliesTo: c.applies_to,
    active: c.active,
    usedCount: c.used_count,
    createdAt: c.created_at,
  };
}

function toBody(draft: Partial<CouponDraft>): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if (draft.code !== undefined) body.code = draft.code;
  if (draft.kind !== undefined) body.kind = draft.kind;
  if (draft.value !== undefined) body.value = draft.value;
  if (draft.minOrder !== undefined) body.min_order = draft.minOrder;
  if (draft.maxDiscount !== undefined) body.max_discount = draft.maxDiscount;
  if (draft.validFrom !== undefined) body.valid_from = draft.validFrom;
  if (draft.validTo !== undefined) body.valid_to = draft.validTo;
  if (draft.usageLimit !== undefined) body.usage_limit = draft.usageLimit;
  if (draft.perUserLimit !== undefined) body.per_user_limit = draft.perUserLimit;
  if (draft.appliesTo !== undefined) body.applies_to = draft.appliesTo;
  if (draft.active !== undefined) body.active = draft.active;
  return body;
}

export const realCouponsApi = {
  async validate({ code, appliesTo, amount }: CouponValidateRequest): Promise<CouponValidateResponse> {
    const r = await request<WireCouponValidateResponse>('/coupons/validate', {
      method: 'POST',
      body: { code, applies_to: appliesTo, amount },
    });
    return { valid: r.valid, discount: r.discount, finalAmount: r.final_amount, reason: r.reason, message: r.message };
  },

  async list(): Promise<Paginated<Coupon>> {
    const result = await request<Paginated<WireCoupon>>('/coupons');
    return { ...result, results: result.results.map(fromWireCoupon) };
  },

  async create(draft: CouponDraft): Promise<Coupon> {
    return fromWireCoupon(await request<WireCoupon>('/coupons', { method: 'POST', body: toBody(draft) }));
  },

  async update(id: number, patch: Partial<CouponDraft>): Promise<Coupon> {
    return fromWireCoupon(await request<WireCoupon>(`/coupons/${id}`, { method: 'PATCH', body: toBody(patch) }));
  },

  async remove(id: number): Promise<void> {
    await request(`/coupons/${id}`, { method: 'DELETE' });
  },
};
