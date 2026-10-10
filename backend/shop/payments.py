"""The purchase flow and the mock payment gateway.

Plan: "Mock payment gateway. One internal function that takes an order and a
test outcome (success, failure, or pending) and returns a result. On success
it marks the order paid, creates the Payment row with its idempotency key,
creates tickets or reduces stock, and posts the ledger entry, all in one
transaction."
"""
import uuid
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from finance.models import LedgerEntry
from finance.services import post_entry
from members.models import Membership
from members.services import start_membership

from .models import Order, OrderLine, Payment

User = get_user_model()

SUCCESS, FAILURE, PENDING = 'success', 'failure', 'pending'
OUTCOMES = [SUCCESS, FAILURE, PENDING]

CASH = '1000'
MEMBERSHIP_DUES_REVENUE = '4000'


class IdempotencyConflict(Exception):
    """The idempotency key already paid for a different purchase."""


@dataclass
class PurchaseResult:
    order: Order
    payment: Payment | None
    membership: Membership | None
    # True when nothing was done because this key had already succeeded.
    replayed: bool = False


def process_payment(order, outcome, idempotency_key):
    """The mock gateway. Returns the Payment on success, otherwise None.

    Must run inside a transaction (the caller's): on success the payment,
    the order status, the thing bought and the ledger entry are saved
    together, and if any of them fails none of them is saved.

    Team decision for the other outcomes:
      failure: the order becomes cancelled; nothing else is created.
      pending: the order stays pending; nothing else is created.
    """
    if order.status != Order.Status.PENDING:
        raise ValueError(f'Order {order.pk} is {order.status}; only a pending order can be paid.')
    if outcome not in OUTCOMES:
        raise ValueError(f'Unknown payment outcome {outcome!r}.')

    if outcome == PENDING:
        return None
    if outcome == FAILURE:
        order.status = Order.Status.CANCELLED
        order.save(update_fields=['status', 'updated_at'])
        return None

    gateway_ref = f'mock_{uuid.uuid4().hex}'
    payment = Payment.objects.create(
        order=order,
        amount=order.total,
        idempotency_key=idempotency_key,
        gateway_ref=gateway_ref,
    )
    order.status = Order.Status.PAID
    order.payment_ref = gateway_ref
    order.save(update_fields=['status', 'payment_ref', 'updated_at'])

    for line in order.lines.select_related('plan'):
        _fulfil(line, payment)
    return payment


def _fulfil(line, payment):
    """Deliver what a paid line bought and post its ledger entry."""
    if line.kind != OrderLine.Kind.MEMBERSHIP:
        raise NotImplementedError(f'No fulfilment for {line.kind} lines yet.')

    order = line.order
    line.membership = start_membership(order.buyer, line.plan)
    line.save(update_fields=['membership', 'updated_at'])
    # Plan posting rule: membership payment succeeds -> debit Cash, credit
    # Membership dues revenue, source reference "Membership payment".
    post_entry(
        description=f'Membership dues: {line.plan.name}',
        source_type=LedgerEntry.SourceType.PAYMENT,
        source_id=payment.pk,
        kind=LedgerEntry.Kind.MEMBERSHIP_DUES,
        created_by=order.buyer,
        lines=[
            (CASH, line.amount, 0),
            (MEMBERSHIP_DUES_REVENUE, 0, line.amount),
        ],
    )


def _replay(user, plan, idempotency_key):
    """If this key already paid for exactly this purchase, return that first
    result. None if the key is unused.
    """
    payment = Payment.objects.select_related('order').filter(idempotency_key=idempotency_key).first()
    if payment is None:
        return None
    order = payment.order
    lines = list(order.lines.select_related('membership__plan'))
    same_purchase = (
        order.buyer_id == user.pk
        and len(lines) == 1
        and lines[0].kind == OrderLine.Kind.MEMBERSHIP
        and lines[0].plan_id == plan.pk
    )
    if not same_purchase:
        # Never hand one user's order to another, or pretend a different
        # plan was bought.
        raise IdempotencyConflict()
    return PurchaseResult(order=order, payment=payment, membership=lines[0].membership, replayed=True)


def purchase_membership(*, user, plan, outcome, idempotency_key):
    """Buy or renew a plan: order, payment, membership and ledger entry.

    The price comes from the plan row; nothing the client sends affects it.

    ASSUMPTION (plan covers only a successful replay): a key whose attempt
    failed or stayed pending is not remembered, so the same key can be used
    to try again.
    """
    try:
        with transaction.atomic():
            # Row lock on the buyer: one purchase at a time per user. A
            # second request with the same key waits here, then finds the
            # first one's payment below instead of charging again. It also
            # keeps two simultaneous renewals from getting the same dates.
            User.objects.select_for_update().get(pk=user.pk)

            replay = _replay(user, plan, idempotency_key)
            if replay is not None:
                return replay

            order = Order.objects.create(buyer=user, subtotal=plan.price, discount=0, total=plan.price)
            line = OrderLine.objects.create(
                order=order, kind=OrderLine.Kind.MEMBERSHIP, plan=plan, qty=1, unit_price=plan.price,
            )
            payment = process_payment(order, outcome, idempotency_key)
            line.refresh_from_db()
            return PurchaseResult(order=order, payment=payment, membership=line.membership)
    except IntegrityError:
        # Two different users sent the same key at the same moment: the
        # unique constraint stopped the second, and everything it had done
        # was rolled back. _replay now sees the winner's payment and raises
        # IdempotencyConflict. If the key is still unused, the IntegrityError
        # was about something else and is re-raised.
        replay = _replay(user, plan, idempotency_key)
        if replay is not None:
            return replay
        raise
