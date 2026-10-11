"""The Razorpay gateway (test mode), alongside the mock in payments.py.

ASSUMPTION: the whole of this module is beyond the backend plan, which
specifies only the mock gateway.

How a Razorpay purchase differs from a mock one: the money is taken in the
buyer's browser, by Razorpay's checkout, between two of our requests.

  1. start_checkout  validates and prices the purchase exactly as the mock
                     does, saves our Order as PENDING, and asks Razorpay for
                     an order of the same amount.
  2. (browser)       Razorpay's checkout takes the payment and hands the
                     browser a payment id and a signature.
  3. verify_payment  checks the signature with our secret, then runs the
                     same fulfil_paid_order as the mock, in one transaction.

Nothing is held for a pending order (the same rule as the mock's "pending"
outcome), so seats or stock can run out between steps 1 and 3. Then the
buyer has paid for something we cannot deliver: the order is flagged
needs_refund and an audit row is written.

FUTURE WORK: no webhooks (they need a public URL). If the browser never
calls verify after paying, the order stays pending although Razorpay holds
the money. A payment.captured webhook would close that gap, and refunds
could then be issued through the API instead of by hand.
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import ssl
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from audit import services as audit
from events.tickets import SoldOut

from .coupons import CouponLimitReached
from .models import Order, Payment
from .payments import IdempotencyConflict, _result, create_order, fulfil_paid_order
from .stock import OutOfStock

logger = logging.getLogger(__name__)
User = get_user_model()

MOCK, RAZORPAY = 'mock', 'razorpay'
ORDERS_URL = 'https://api.razorpay.com/v1/orders'
CURRENCY = 'INR'
# Without a timeout a dead gateway would hang the request.
TIMEOUT_SECONDS = 10
# Razorpay refuses orders under one rupee.
MIN_AMOUNT = 100
# The operating system's CA bundle on macOS and most Linux systems.
SYSTEM_CA_BUNDLE = '/etc/ssl/cert.pem'


class GatewayUnavailable(Exception):
    """Razorpay could not be reached, or refused the request."""


class GatewayNotEnabled(Exception):
    """The server is running on the mock gateway."""


class AmountTooSmall(Exception):
    """The order total is below what Razorpay accepts."""


class OrderNotFound(Exception):
    """No such Razorpay checkout belonging to this user."""


class InvalidSignature(Exception):
    """The signature does not match; the payment is not proven."""


class OrderAlreadyPaid(Exception):
    """The order was already paid (by another payment, or before a cancel)."""


class SoldOutAfterPayment(Exception):
    """Paid, but the seats or stock were gone. Flagged for refund."""


class CouponGoneAfterPayment(Exception):
    """Paid at the coupon's price, but the coupon was used up meanwhile.
    Flagged for refund."""


def active_gateway():
    """Which gateway this server is using: "mock" or "razorpay"."""
    if settings.PAYMENT_GATEWAY != RAZORPAY:
        return MOCK
    if not (settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET):
        logger.warning(
            'PAYMENT_GATEWAY is "razorpay" but RAZORPAY_KEY_ID or RAZORPAY_KEY_SECRET is empty; '
            'using the mock gateway instead.'
        )
        return MOCK
    return RAZORPAY


def _require_razorpay():
    if active_gateway() != RAZORPAY:
        raise GatewayNotEnabled()


# Talking to Razorpay -------------------------------------------------------

def tls_context():
    """Certificate and hostname checks are always on. Some Python installs
    (python.org's macOS build, for one) ship with no CA certificates, and
    then no HTTPS site can be verified; in that case the operating system's
    bundle is loaded. Verification is never switched off.
    """
    context = ssl.create_default_context()
    if not context.cert_store_stats()['x509_ca'] and os.path.exists(SYSTEM_CA_BUNDLE):
        context.load_verify_locations(SYSTEM_CA_BUNDLE)
    return context


def create_gateway_order(*, amount, receipt):
    """Ask Razorpay for an order of `amount` paise. Returns its id.

    Standard library only (no new dependency). The secret travels only in
    the Authorization header of this HTTPS request and is never logged.
    """
    credentials = f'{settings.RAZORPAY_KEY_ID}:{settings.RAZORPAY_KEY_SECRET}'.encode()
    request = Request(
        ORDERS_URL,
        data=json.dumps({'amount': amount, 'currency': CURRENCY, 'receipt': receipt}).encode(),
        headers={
            'Authorization': 'Basic ' + base64.b64encode(credentials).decode(),
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS, context=tls_context()) as response:
            body = json.loads(response.read())
    except HTTPError as exc:
        # Razorpay answered, but with an error (bad keys, bad amount...).
        logger.error('Razorpay refused to create an order: HTTP %s', exc.code)
        raise GatewayUnavailable() from exc
    except (OSError, ValueError) as exc:
        # OSError covers URLError, timeouts and refused connections;
        # ValueError covers a reply that is not JSON.
        # The reason is logged (it names no credential): a TLS or DNS
        # problem is otherwise very hard to tell apart from an outage.
        logger.error('Razorpay could not be reached: %s: %s', type(exc).__name__, getattr(exc, 'reason', exc))
        raise GatewayUnavailable() from exc

    gateway_id = body.get('id') if isinstance(body, dict) else None
    if not isinstance(gateway_id, str) or not gateway_id or body.get('amount') != amount:
        logger.error('Razorpay returned an unexpected order.')
        raise GatewayUnavailable()
    return gateway_id


def signature_is_valid(razorpay_order_id, razorpay_payment_id, signature):
    """Razorpay signs "<order id>|<payment id>" with our key secret
    (HMAC-SHA256, hex). Only Razorpay and this server know the secret, so a
    matching signature proves Razorpay took this payment for this order.
    """
    expected = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode(),
        f'{razorpay_order_id}|{razorpay_payment_id}'.encode(),
        hashlib.sha256,
    ).hexdigest()
    # compare_digest takes the same time wherever the first difference is,
    # so the response time does not leak how much of a guess was right.
    return hmac.compare_digest(expected.encode(), signature.encode())


# Step 1: start a checkout --------------------------------------------------

def start_checkout(*, user, idempotency_key, same_purchase, build_lines, coupon=''):
    """Create (or find) the buyer's pending order and its Razorpay order.

    Returns (order, created). created is False when this key had already
    started the same checkout, in which case nothing new is made.

    same_purchase and build_lines are a basket from payments.py, the same
    one the mock gateway would use.
    """
    _require_razorpay()
    try:
        with transaction.atomic():
            # Same first lock as the mock purchase: one at a time per buyer.
            User.objects.select_for_update().get(pk=user.pk)
            order, created = _pending_order(user, idempotency_key, same_purchase, build_lines, coupon)
    except IntegrityError:
        # Another user started a checkout with this key at the same moment.
        raise IdempotencyConflict()

    if order.razorpay_order_id:
        return order, created

    # The call to Razorpay is made here, after the transaction has ended,
    # so no row lock is held while waiting on the network.
    try:
        gateway_id = create_gateway_order(amount=order.total, receipt=str(order.pk))
    except GatewayUnavailable:
        # No checkout can open for this order, so it is closed. The key is
        # then free to try again.
        Order.objects.filter(pk=order.pk, status=Order.Status.PENDING, razorpay_order_id='').update(
            status=Order.Status.CANCELLED, idempotency_key='',
        )
        raise
    order.razorpay_order_id = gateway_id
    order.save(update_fields=['razorpay_order_id', 'updated_at'])
    return order, created


def _pending_order(user, idempotency_key, same_purchase, build_lines, coupon):
    if Payment.objects.filter(idempotency_key=idempotency_key).exists():
        raise IdempotencyConflict()
    existing = Order.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        # The key started a checkout before. Hand it back only if it is the
        # same buyer, the same purchase, and still open.
        if (
            existing.buyer_id != user.pk
            or existing.status != Order.Status.PENDING
            or not same_purchase(list(existing.lines.all()))
        ):
            raise IdempotencyConflict()
        return existing, False

    order = create_order(user, build_lines(), coupon_code=coupon, idempotency_key=idempotency_key)
    if order.total < MIN_AMOUNT:
        raise AmountTooSmall()  # rolls the order back
    return order, True


# Step 3: verify the payment ------------------------------------------------

def _locked_order(user, order_id):
    """The buyer's Razorpay order, row-locked. Buyer first, then the order:
    the same lock order as every other purchase, so they cannot deadlock.
    """
    User.objects.select_for_update().get(pk=user.pk)
    order = (
        Order.objects.select_for_update()
        .filter(pk=order_id, buyer=user).exclude(razorpay_order_id='').first()
    )
    if order is None:
        # Someone else's order looks exactly like one that does not exist.
        raise OrderNotFound()
    return order


def verify_payment(*, user, order_id, razorpay_order_id, razorpay_payment_id, signature):
    """Check the signature and, if it is genuine, deliver the order.

    Returns a PurchaseResult, the same as a mock purchase. Safe to call
    twice with the same payment: the second call changes nothing and returns
    the first result with replayed=True.
    """
    _require_razorpay()
    try:
        with transaction.atomic():
            order = _locked_order(user, order_id)
            # The signature is checked against the Razorpay order id WE
            # stored, never one the client chooses.
            if razorpay_order_id != order.razorpay_order_id or not signature_is_valid(
                order.razorpay_order_id, razorpay_payment_id, signature,
            ):
                raise InvalidSignature()

            if order.status == Order.Status.PAID:
                payment = order.payments.get()
                if payment.gateway_ref != razorpay_payment_id:
                    raise OrderAlreadyPaid()
                return _result(order, payment, list(order.lines.select_related('membership__plan')), replayed=True)
            if order.needs_refund:
                # Flagged by an earlier call; give the same answer again.
                raise REFUND_ERRORS[_refund_reason(order)]()
            if order.status == Order.Status.CANCELLED:
                # The buyer closed the checkout, yet Razorpay proves they
                # paid (the two events can race). They paid, so deliver.
                order.status = Order.Status.PENDING

            payment = fulfil_paid_order(
                order, gateway_ref=razorpay_payment_id, idempotency_key=order.idempotency_key,
            )
            return _result(order, payment, list(order.lines.select_related('membership__plan')))
    except (SoldOut, OutOfStock):
        # The transaction above was rolled back in full: no payment row, no
        # tickets, no stock taken, no ledger entry.
        _flag_for_refund(user, order_id, razorpay_payment_id, 'sold_out')
        raise SoldOutAfterPayment()
    except CouponLimitReached:
        _flag_for_refund(user, order_id, razorpay_payment_id, 'coupon_limit_reached')
        raise CouponGoneAfterPayment()


REFUND_ERRORS = {'sold_out': SoldOutAfterPayment, 'coupon_limit_reached': CouponGoneAfterPayment}


def _refund_reason(order):
    """Why an order was flagged, read back from its audit row."""
    from audit.models import AuditLog

    log = AuditLog.objects.filter(
        action='order.refund_due', object_type='shop.order', object_id=order.pk,
    ).order_by('-id').first()
    reason = (log.after or {}).get('reason') if log else None
    return reason if reason in REFUND_ERRORS else 'sold_out'


def _flag_for_refund(user, order_id, razorpay_payment_id, reason):
    with transaction.atomic():
        order = _locked_order(user, order_id)
        if order.status == Order.Status.PAID or order.needs_refund:
            return
        before = {'status': order.status, 'needs_refund': False}
        order.status = Order.Status.CANCELLED
        order.needs_refund = True
        order.payment_ref = razorpay_payment_id
        order.save(update_fields=['status', 'needs_refund', 'payment_ref', 'updated_at'])
        audit.record(
            actor=user, action='order.refund_due', obj=order, before=before,
            after={
                'status': order.status, 'needs_refund': True, 'reason': reason,
                'amount': order.total, 'razorpay_order_id': order.razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
            },
        )


# The buyer closed the checkout ---------------------------------------------

def cancel_checkout(*, user, order_id):
    """Pending -> cancelled. Calling it again changes nothing."""
    _require_razorpay()
    with transaction.atomic():
        order = _locked_order(user, order_id)
        if order.status == Order.Status.PAID:
            raise OrderAlreadyPaid()
        if order.status == Order.Status.PENDING:
            order.status = Order.Status.CANCELLED
            order.save(update_fields=['status', 'updated_at'])
        return order
