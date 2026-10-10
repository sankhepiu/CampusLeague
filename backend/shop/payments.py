"""The purchase flow and the mock payment gateway.

Plan: "Mock payment gateway. One internal function that takes an order and a
test outcome (success, failure, or pending) and returns a result. On success
it marks the order paid, creates the Payment row with its idempotency key,
creates tickets or reduces stock, and posts the ledger entry, all in one
transaction."
"""
import uuid
from dataclasses import dataclass, field

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from events.models import Event, Ticket, TicketTier
from events.tickets import SoldOut, issue_tickets
from finance.models import LedgerEntry
from finance.services import post_entry
from members.models import Membership
from members.services import membership_status, start_membership

from .models import Order, OrderLine, Payment

User = get_user_model()

SUCCESS, FAILURE, PENDING = 'success', 'failure', 'pending'
OUTCOMES = [SUCCESS, FAILURE, PENDING]

CASH = '1000'
MEMBERSHIP_DUES_REVENUE = '4000'


class IdempotencyConflict(Exception):
    """The idempotency key already paid for a different purchase."""


class SalesClosed(Exception):
    """The event is not on sale, or the tier's sale window is not open."""


@dataclass
class PurchaseResult:
    order: Order
    payment: Payment | None
    membership: Membership | None = None
    tickets: list[Ticket] = field(default_factory=list)
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

    for line in order.lines.select_related('order__buyer', 'plan', 'tier__event'):
        _fulfil(line, payment)
    return payment


def _fulfil(line, payment):
    """Deliver what a paid line bought and post its ledger entry."""
    if line.kind == OrderLine.Kind.TICKET:
        issue_tickets(line, payment)
        return
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


def _replay(user, idempotency_key, **wanted):
    """If this key already paid for exactly this purchase, return that first
    result. None if the key is unused.

    wanted describes the single order line the request asks for, for example
    kind='membership', plan_id=3.
    """
    payment = Payment.objects.select_related('order').filter(idempotency_key=idempotency_key).first()
    if payment is None:
        return None
    order = payment.order
    lines = list(order.lines.select_related('membership__plan'))
    same_purchase = (
        order.buyer_id == user.pk
        and len(lines) == 1
        and all(getattr(lines[0], name) == value for name, value in wanted.items())
    )
    if not same_purchase:
        # Never hand one user's order to another, or pretend a different
        # purchase was made.
        raise IdempotencyConflict()
    return PurchaseResult(
        order=order, payment=payment, membership=lines[0].membership,
        tickets=list(order.tickets.select_related('event', 'tier').order_by('id')), replayed=True,
    )


def _purchase(*, user, idempotency_key, outcome, wanted, build_line):
    """Shared purchase skeleton: lock, replay check, order, payment.

    build_line() runs inside the transaction after the buyer is locked. It
    returns the fields of the one order line to create (and may take further
    locks and raise to refuse the sale before anything is written).

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

            replay = _replay(user, idempotency_key, **wanted)
            if replay is not None:
                return replay

            line_fields = build_line()
            amount = line_fields['qty'] * line_fields['unit_price']
            order = Order.objects.create(buyer=user, subtotal=amount, discount=0, total=amount)
            line = OrderLine.objects.create(order=order, **line_fields)
            payment = process_payment(order, outcome, idempotency_key)
            line.refresh_from_db()
            return PurchaseResult(
                order=order, payment=payment, membership=line.membership,
                tickets=list(order.tickets.select_related('event', 'tier').order_by('id')),
            )
    except IntegrityError:
        # Two different users sent the same key at the same moment: the
        # unique constraint stopped the second, and everything it had done
        # was rolled back. _replay now sees the winner's payment and raises
        # IdempotencyConflict. If the key is still unused, the IntegrityError
        # was about something else and is re-raised.
        replay = _replay(user, idempotency_key, **wanted)
        if replay is not None:
            return replay
        raise


def purchase_membership(*, user, plan, outcome, idempotency_key):
    """Buy or renew a plan: order, payment, membership and ledger entry.

    The price comes from the plan row; nothing the client sends affects it.
    """
    kind = OrderLine.Kind.MEMBERSHIP
    return _purchase(
        user=user, idempotency_key=idempotency_key, outcome=outcome,
        wanted={'kind': kind, 'plan_id': plan.pk},
        build_line=lambda: {'kind': kind, 'plan': plan, 'qty': 1, 'unit_price': plan.price},
    )


def ticket_price(tier, user):
    """Team decision: member_price if the buyer has an active membership at
    purchase time, otherwise public_price. No stacking with plan discounts.
    """
    return tier.member_price if membership_status(user) == 'active' else tier.public_price


def purchase_tickets(*, user, tier_id, quantity, outcome, idempotency_key):
    """Buy seats in one tier: order, payment, tickets and ledger entry.

    Plan, overselling seats: "In one transaction: lock the ticket tier row,
    check sold_count < capacity, create tickets, increment sold_count."
    Raises SoldOut or SalesClosed before anything is written.
    """
    kind = OrderLine.Kind.TICKET

    def build_line():
        # Row lock on the tier, held until this transaction ends. A second
        # buyer of the same tier waits here and then reads the updated
        # sold_count, so two buyers can never both see "1 seat left".
        # Lock order is always buyer, then tier, so two purchases cannot
        # deadlock each other.
        tier = TicketTier.objects.select_for_update(of=('self',)).select_related('event').get(pk=tier_id)
        now = timezone.now()
        if (
            tier.event.status != Event.Status.ON_SALE
            or (tier.sale_opens and now < tier.sale_opens)
            or (tier.sale_closes and now >= tier.sale_closes)
        ):
            raise SalesClosed()
        # Seats are only taken on success, but a sold-out tier is refused
        # for every outcome so no pointless order is created.
        if tier.seats_left < quantity:
            raise SoldOut()
        return {'kind': kind, 'tier': tier, 'qty': quantity, 'unit_price': ticket_price(tier, user)}

    return _purchase(
        user=user, idempotency_key=idempotency_key, outcome=outcome,
        wanted={'kind': kind, 'tier_id': tier_id, 'qty': quantity},
        build_line=build_line,
    )
