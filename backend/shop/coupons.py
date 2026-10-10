"""Coupons: working out the discount, and counting a use when it is paid.

ASSUMPTION: all of this is beyond the backend plan.

Price order (team decision): sale price, then member discount, then coupon.
The coupon is worked out on what is left after the first two.

ASSUMPTION: a coupon never makes an order free. Every order has a payment
and a ledger entry behind it, and neither can be for zero, so the discount
stops at MIN_TOTAL short of the whole amount.

Ledger (ASSUMPTION): unchanged. Revenue is posted at the amount actually
paid, net of every discount, exactly as before; the coupon and the discount
it gave are kept on the Order and its lines for reporting.
"""
from django.db.models import F
from django.utils import timezone

from .models import Coupon, CouponRedemption

# One rupee: the least an order can cost (also Razorpay's minimum charge).
MIN_TOTAL = 100

REASONS = {
    'not_found': 'There is no coupon with this code.',
    'inactive': 'This coupon is no longer active.',
    'not_started': 'This coupon is not valid yet.',
    'expired': 'This coupon has expired.',
    'not_applicable': 'This coupon cannot be used for this kind of purchase.',
    'min_order_not_met': 'The order is below the minimum amount for this coupon.',
    'usage_limit_reached': 'This coupon has been used up.',
    'already_used': 'You have already used this coupon.',
    'no_discount': 'The order is too small for this coupon to take anything off.',
}

# OrderLine.kind -> the coupon's applies_to value.
PURPOSE_BY_KIND = {'membership': 'membership', 'ticket': 'tickets', 'merch': 'merch'}


class CouponInvalid(Exception):
    """The coupon cannot be used for this purchase. Nothing was written."""

    def __init__(self, reason):
        self.reason = reason
        self.message = REASONS[reason]
        super().__init__(self.message)


class CouponLimitReached(Exception):
    """The coupon ran out between checkout and payment."""


def normalise(code):
    return (code or '').strip().upper()


def find(code, lock=False):
    """The coupon with this code, in any letter case. With lock=True the
    row is locked until the transaction ends, so two buyers of the last use
    are handled one after the other.
    """
    coupons = Coupon.objects.select_for_update() if lock else Coupon.objects
    return coupons.filter(code=normalise(code)).first()


def evaluate(coupon, purpose, amount, user, now=None):
    """Return (discount, reason). reason is None when the coupon applies;
    otherwise discount is 0 and reason is a key of REASONS.

    amount is what the purchase costs before the coupon, in paise.
    """
    now = now or timezone.now()
    if coupon is None:
        return 0, 'not_found'
    if not coupon.active:
        return 0, 'inactive'
    if coupon.valid_from and now < coupon.valid_from:
        return 0, 'not_started'
    if coupon.valid_to and now >= coupon.valid_to:
        return 0, 'expired'
    if coupon.applies_to not in (Coupon.AppliesTo.ALL, purpose):
        return 0, 'not_applicable'
    if amount < coupon.min_order:
        return 0, 'min_order_not_met'
    if coupon.usage_limit is not None and coupon.used_count >= coupon.usage_limit:
        return 0, 'usage_limit_reached'
    if user is not None and uses_by(coupon, user) >= coupon.per_user_limit:
        return 0, 'already_used'

    # Rounded down, like the member discount: never a fraction of a paisa.
    discount = amount * coupon.value // 100 if coupon.kind == Coupon.Kind.PERCENT else coupon.value
    if coupon.max_discount is not None:
        discount = min(discount, coupon.max_discount)
    discount = min(discount, amount - MIN_TOTAL)
    if discount <= 0:
        return 0, 'no_discount'
    return discount, None


def uses_by(coupon, user):
    return CouponRedemption.objects.filter(coupon=coupon, user=user).count()


def apply(code, user, line_fields):
    """Work the coupon into the lines of an order about to be created.

    Runs inside the purchase transaction, after the buyer and the tier or
    stock rows are locked. Locks the coupon row, checks it, and spreads its
    discount over the lines in proportion to what each costs. Returns
    (coupon, discount), or (None, 0) when no code was given. Raises
    CouponInvalid.
    """
    if not normalise(code):
        return None, 0
    coupon = find(code, lock=True)
    amounts = [fields['qty'] * fields['unit_price'] - fields.get('discount', 0) for fields in line_fields]
    purpose = PURPOSE_BY_KIND[line_fields[0]['kind']]
    discount, reason = evaluate(coupon, purpose, sum(amounts), user)
    if reason:
        raise CouponInvalid(reason)

    # Proportional shares, rounded down; the last line takes what rounding
    # left over, so the shares add up to the discount exactly.
    left = discount
    for index, (fields, amount) in enumerate(zip(line_fields, amounts)):
        share = left if index == len(line_fields) - 1 else discount * amount // sum(amounts)
        share = min(share, amount)
        left -= share
        fields['coupon_discount'] = share
        fields['discount'] = fields.get('discount', 0) + share
    return coupon, discount - left


def redeem(order):
    """Count one use of the order's coupon. Called by fulfil_paid_order, so
    it happens only when the payment has succeeded, in that transaction.

    The limits are checked again here under the row lock: for Razorpay,
    time has passed since checkout and the last use may have gone.
    """
    if order.coupon_id is None:
        return
    coupon = Coupon.objects.select_for_update().get(pk=order.coupon_id)
    if coupon.usage_limit is not None and coupon.used_count >= coupon.usage_limit:
        raise CouponLimitReached()
    if uses_by(coupon, order.buyer) >= coupon.per_user_limit:
        raise CouponLimitReached()
    CouponRedemption.objects.create(
        coupon=coupon, user=order.buyer, order=order, discount=order.coupon_discount,
    )
    Coupon.objects.filter(pk=coupon.pk).update(used_count=F('used_count') + 1, updated_at=timezone.now())
