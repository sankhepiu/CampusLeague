"""API pieces shared by every purchase endpoint."""
import re

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


def idempotency_key(request):
    key = request.headers.get('Idempotency-Key', '')
    if not IDEMPOTENCY_KEY_PATTERN.fullmatch(key):
        raise IdempotencyKeyRequired()
    return key
