import { useEffect, useState } from 'react';
import { couponsApi } from './api';
import type { CouponValidateAppliesTo, CouponValidateResponse } from './types';

export interface CouponState {
  code: string;
  setCode: (code: string) => void;
  checking: boolean;
  result: CouponValidateResponse | null;
  /** The code to send with the purchase, only once the server has said it
   * is valid for this amount; otherwise undefined. */
  applied: string | undefined;
  /** Paise the coupon takes off; 0 unless it is valid. */
  discount: number;
}

/** A coupon code checked against POST /coupons/validate as the user types
 * (and again whenever the amount changes, since a minimum order may apply).
 * The estimate is for display; the server prices the order when it is paid. */
export function useCoupon(appliesTo: CouponValidateAppliesTo, amount: number): CouponState {
  const [code, setCode] = useState('');
  const [result, setResult] = useState<CouponValidateResponse | null>(null);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    const trimmed = code.trim();
    if (!trimmed || amount <= 0) return;
    let stale = false;
    const timer = setTimeout(() => {
      setChecking(true);
      couponsApi
        .validate({ code: trimmed, appliesTo, amount })
        .catch((): CouponValidateResponse => ({ valid: false, discount: 0, finalAmount: amount, reason: null, message: 'Could not check this coupon.' }))
        .then((response) => {
          if (stale) return;
          setResult(response);
          setChecking(false);
        });
    }, 400);
    return () => {
      stale = true;
      clearTimeout(timer);
    };
  }, [code, appliesTo, amount]);

  // An empty field has no result, whatever an earlier check said.
  const current = code.trim() && amount > 0 ? result : null;
  const valid = current?.valid === true;
  return {
    code,
    setCode: (next) => setCode(next.toUpperCase()),
    checking: checking && !!code.trim(),
    result: current,
    applied: valid ? code.trim().toUpperCase() : undefined,
    discount: valid ? current.discount : 0,
  };
}
