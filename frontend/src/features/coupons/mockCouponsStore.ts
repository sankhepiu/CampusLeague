import { ApiRequestError } from '../../api/client';
import type { AuthUser } from '../auth/types';
import type { Coupon, CouponAppliesTo, CouponDraft, CouponInvalidReason, CouponValidateAppliesTo, CouponValidateResponse } from './types';

interface MockCoupon extends Coupon {
  usesByUser: Record<string, number>;
}

const STORE_KEY = 'campusleague.mock.coupons';
const daysAgo = (n: number) => new Date(Date.now() - n * 86_400_000).toISOString();

function seed(): MockCoupon[] {
  return [
    {
      id: 1,
      code: 'WELCOME10',
      kind: 'percent',
      value: 10,
      minOrder: 0,
      maxDiscount: null,
      validFrom: null,
      validTo: null,
      usageLimit: null,
      perUserLimit: 1,
      appliesTo: 'membership',
      active: true,
      usedCount: 0,
      createdAt: daysAgo(60),
      usesByUser: {},
    },
    {
      id: 2,
      code: 'GALA50',
      kind: 'flat',
      value: 5000,
      minOrder: 20000,
      maxDiscount: null,
      validFrom: null,
      validTo: null,
      usageLimit: null,
      perUserLimit: 1,
      appliesTo: 'tickets',
      active: true,
      usedCount: 0,
      createdAt: daysAgo(45),
      usesByUser: {},
    },
    {
      id: 3,
      code: 'MERCH20',
      kind: 'percent',
      value: 20,
      minOrder: 0,
      maxDiscount: 15000,
      validFrom: null,
      validTo: null,
      usageLimit: 5,
      perUserLimit: 1,
      appliesTo: 'merch',
      active: true,
      usedCount: 0,
      createdAt: daysAgo(30),
      usesByUser: {},
    },
  ];
}

function loadStore(): MockCoupon[] {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) return JSON.parse(raw) as MockCoupon[];
  } catch {
    /* storage unavailable or corrupt */
  }
  const seeded = seed();
  saveStore(seeded);
  return seeded;
}

function saveStore(coupons: MockCoupon[]): void {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(coupons));
  } catch {
    /* storage unavailable */
  }
}

function nextId(items: { id: number }[]): number {
  return items.reduce((max, i) => Math.max(max, i.id), 0) + 1;
}

function toPublic(c: MockCoupon): Coupon {
  const { usesByUser: _usesByUser, ...rest } = c;
  return rest;
}

const APPLIES_MATCH: Record<CouponAppliesTo, CouponValidateAppliesTo[]> = {
  all: ['merch', 'tickets', 'membership'],
  merch: ['merch'],
  tickets: ['tickets'],
  membership: ['membership'],
};

/** Pure "what would this code take off" check — changes and reserves
 * nothing, matching POST /coupons/validate. */
function evaluate(coupon: MockCoupon, appliesTo: CouponValidateAppliesTo, amount: number, userEmail: string | undefined): CouponValidateResponse {
  const invalid = (reason: CouponInvalidReason, message: string): CouponValidateResponse => ({ valid: false, discount: 0, finalAmount: amount, reason, message });

  if (!coupon.active) return invalid('inactive', 'This coupon is switched off.');
  const now = Date.now();
  if (coupon.validFrom && now < new Date(coupon.validFrom).getTime()) return invalid('not_started', 'This coupon is not active yet.');
  if (coupon.validTo && now > new Date(coupon.validTo).getTime()) return invalid('expired', 'This coupon has expired.');
  if (!APPLIES_MATCH[coupon.appliesTo].includes(appliesTo)) return invalid('not_applicable', 'This coupon does not apply to this purchase.');
  if (amount < coupon.minOrder) return invalid('min_order_not_met', `This coupon needs an order of at least ₹${(coupon.minOrder / 100).toFixed(2)}.`);
  if (coupon.usageLimit !== null && coupon.usedCount >= coupon.usageLimit) return invalid('usage_limit_reached', 'This coupon has been fully used.');
  if (userEmail && (coupon.usesByUser[userEmail] ?? 0) >= coupon.perUserLimit) return invalid('already_used', 'You have already used this coupon.');

  const raw = coupon.kind === 'percent' ? Math.floor((amount * coupon.value) / 100) : coupon.value;
  const capped = coupon.maxDiscount !== null ? Math.min(raw, coupon.maxDiscount) : raw;
  // Never free: an order can never go below 100 paise (Rs 1).
  const discount = Math.min(capped, Math.max(0, amount - 100));

  if (discount <= 0) return invalid('no_discount', 'This purchase is too small for the coupon to take anything off.');

  return { valid: true, discount, finalAmount: amount - discount, reason: null, message: null };
}

export function validateMockCoupon(code: string, appliesTo: CouponValidateAppliesTo, amount: number, userEmail: string | undefined): CouponValidateResponse {
  const coupon = loadStore().find((c) => c.code === code.trim().toUpperCase());
  if (!coupon) return { valid: false, discount: 0, finalAmount: amount, reason: 'not_found', message: 'No coupon has this code.' };
  return evaluate(coupon, appliesTo, amount, userEmail);
}

/** Validates AND commits a use (increments counts) — called only once a
 * purchase actually succeeds, matching "a use is counted only when the
 * payment succeeds." Returns no discount/coupon when `code` is empty. */
export function applyMockCoupon({
  code,
  appliesTo,
  amount,
  user,
}: {
  code: string | undefined;
  appliesTo: CouponValidateAppliesTo;
  amount: number;
  user: AuthUser | undefined;
}): { discount: number; coupon: string | null } {
  if (!code || !code.trim()) return { discount: 0, coupon: null };

  const store = loadStore();
  const coupon = store.find((c) => c.code === code.trim().toUpperCase());
  if (!coupon) throw new ApiRequestError({ code: 'coupon_invalid', message: 'No coupon has this code.', field: 'coupon' });

  const result = evaluate(coupon, appliesTo, amount, user?.email);
  if (!result.valid) {
    throw new ApiRequestError({ code: 'coupon_invalid', message: result.message ?? 'This coupon cannot be used.', field: 'coupon' });
  }

  coupon.usedCount += 1;
  if (user) coupon.usesByUser[user.email] = (coupon.usesByUser[user.email] ?? 0) + 1;
  saveStore(store);

  return { discount: result.discount, coupon: coupon.code };
}

export const mockCoupons = {
  list(): Coupon[] {
    return loadStore()
      .map(toPublic)
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  },

  get(id: number): Coupon {
    const coupon = loadStore().find((c) => c.id === id);
    if (!coupon) throw new ApiRequestError({ code: 'not_found', message: 'No such coupon.' });
    return toPublic(coupon);
  },

  create(draft: CouponDraft): Coupon {
    const store = loadStore();
    const code = draft.code.trim().toUpperCase();
    if (!/^[A-Z0-9_-]{3,20}$/.test(code)) {
      throw new ApiRequestError({ code: 'validation_error', message: 'Code must be 3 to 20 letters, digits, - or _.', field: 'code' });
    }
    if (store.some((c) => c.code === code)) {
      throw new ApiRequestError({ code: 'validation_error', message: 'A coupon with this code already exists.', field: 'code' });
    }
    if (draft.kind === 'percent' && (draft.value < 1 || draft.value > 100)) {
      throw new ApiRequestError({ code: 'validation_error', message: 'A percent coupon must be 1 to 100.', field: 'value' });
    }
    if (draft.kind === 'flat' && (draft.value < 1 || draft.value > 1_000_000_000)) {
      throw new ApiRequestError({ code: 'validation_error', message: 'A flat coupon must be greater than zero.', field: 'value' });
    }
    if (draft.validFrom && draft.validTo && draft.validTo <= draft.validFrom) {
      throw new ApiRequestError({ code: 'validation_error', message: 'Valid-to must be after valid-from.', field: 'valid_to' });
    }
    const coupon: MockCoupon = {
      id: nextId(store),
      code,
      kind: draft.kind,
      value: draft.value,
      minOrder: draft.minOrder ?? 0,
      maxDiscount: draft.maxDiscount ?? null,
      validFrom: draft.validFrom ?? null,
      validTo: draft.validTo ?? null,
      usageLimit: draft.usageLimit ?? null,
      perUserLimit: draft.perUserLimit ?? 1,
      appliesTo: draft.appliesTo ?? 'all',
      active: draft.active ?? true,
      usedCount: 0,
      createdAt: new Date().toISOString(),
      usesByUser: {},
    };
    store.push(coupon);
    saveStore(store);
    return toPublic(coupon);
  },

  update(id: number, patch: Partial<CouponDraft>): Coupon {
    const store = loadStore();
    const coupon = store.find((c) => c.id === id);
    if (!coupon) throw new ApiRequestError({ code: 'not_found', message: 'No such coupon.' });
    if (patch.usageLimit !== undefined && patch.usageLimit !== null && patch.usageLimit < coupon.usedCount) {
      throw new ApiRequestError({ code: 'validation_error', message: `Cannot be set below the ${coupon.usedCount} uses already recorded.`, field: 'usage_limit' });
    }
    Object.assign(coupon, {
      kind: patch.kind ?? coupon.kind,
      value: patch.value ?? coupon.value,
      minOrder: patch.minOrder ?? coupon.minOrder,
      maxDiscount: patch.maxDiscount !== undefined ? patch.maxDiscount : coupon.maxDiscount,
      validFrom: patch.validFrom !== undefined ? patch.validFrom : coupon.validFrom,
      validTo: patch.validTo !== undefined ? patch.validTo : coupon.validTo,
      usageLimit: patch.usageLimit !== undefined ? patch.usageLimit : coupon.usageLimit,
      perUserLimit: patch.perUserLimit ?? coupon.perUserLimit,
      appliesTo: patch.appliesTo ?? coupon.appliesTo,
      active: patch.active !== undefined ? patch.active : coupon.active,
    });
    saveStore(store);
    return toPublic(coupon);
  },

  remove(id: number): void {
    const store = loadStore();
    const coupon = store.find((c) => c.id === id);
    if (!coupon) throw new ApiRequestError({ code: 'not_found', message: 'No such coupon.' });
    if (coupon.usedCount > 0) {
      throw new ApiRequestError({ code: 'coupon_in_use', message: 'This coupon has been used on an order — set it inactive instead.' });
    }
    saveStore(store.filter((c) => c.id !== id));
  },
};
