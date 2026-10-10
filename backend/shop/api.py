"""API pieces shared by every purchase endpoint."""
import re
from contextlib import contextmanager

from rest_framework import status
from rest_framework.exceptions import APIException

# ASSUMPTION (plan names the key but not how it travels): sent in the
# Idempotency-Key header; 8 to 64 letters, digits, "-" or "_". A UUID fits.
IDEMPOTENCY_KEY_PATTERN = re.compile(r'^[A-Za-z0-9_-]{8,64}$')


class IdempotencyKeyRequired(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Send an Idempotency-Key header: 8 to 64 letters, digits, "-" or "_".'
    default_code = 'idempotency_key_required'


class IdempotencyKeyReused(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = 'This Idempotency-Key was already used for a different purchase.'
    default_code = 'idempotency_key_reused'


class PaymentFailed(APIException):
    status_code = status.HTTP_402_PAYMENT_REQUIRED
    default_detail = 'The payment was declined. You have not been charged.'
    default_code = 'payment_failed'


class MockGatewayDisabled(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = 'This server takes payments through Razorpay. Start the purchase with POST /payments/razorpay/order.'
    default_code = 'gateway_not_enabled'


class CouponInvalidError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'This coupon cannot be used.'
    default_code = 'coupon_invalid'


class CouponLimitReachedError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = 'This coupon has just been used up. You have not been charged.'
    default_code = 'coupon_limit_reached'


def require_mock_gateway():
    """The mock purchase endpoints give things away for a test flag, so they
    are closed whenever a real gateway is configured.
    """
    from . import razorpay

    if razorpay.active_gateway() != razorpay.MOCK:
        raise MockGatewayDisabled()


@contextmanager
def purchase_errors():
    """Turns the purchase service's shared exceptions into API errors. Each
    view adds its own (sold out, out of stock) around this.
    """
    from .coupons import CouponInvalid, CouponLimitReached
    from .payments import IdempotencyConflict

    try:
        yield
    except IdempotencyConflict:
        raise IdempotencyKeyReused()
    except CouponInvalid as exc:
        raise CouponInvalidError(exc.message)
    except CouponLimitReached:
        raise CouponLimitReachedError()


def idempotency_key(request):
    key = request.headers.get('Idempotency-Key', '')
    if not IDEMPOTENCY_KEY_PATTERN.fullmatch(key):
        raise IdempotencyKeyRequired()
    return key
