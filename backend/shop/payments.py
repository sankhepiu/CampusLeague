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
from members.services import current_membership, membership_status, start_membership

from .models import Order, OrderLine, Payment, ProductSize
from .stock import OutOfStock, take_stock

User = get_user_model()

SUCCESS, FAILURE, PENDING = 'success', 'failure', 'pending'
OUTCOMES = [SUCCESS, FAILURE, PENDING]

CASH = '1000'
MEMBERSHIP_DUES_REVENUE = '4000'
MERCH_REVENUE = '4200'


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

    return fulfil_paid_order(order, gateway_ref=f'mock_{uuid.uuid4().hex}', idempotency_key=idempotency_key)


def fulfil_paid_order(order, *, gateway_ref, idempotency_key):
    """The one success path, shared by the mock and Razorpay gateways: the
    Payment row, the order marked paid, the thing bought, the ledger entry.

    Must run inside the caller's transaction, so that if any step fails
    (SoldOut, OutOfStock, a database check) none of them is saved.
    """
    if order.status != Order.Status.PENDING:
        raise ValueError(f'Order {order.pk} is {order.status}; only a pending order can be paid.')
    payment = Payment.objects.create(
        order=order,
        amount=order.total,
        idempotency_key=idempotency_key,
        gateway_ref=gateway_ref,
    )
    order.status = Order.Status.PAID
    order.payment_ref = gateway_ref
    order.save(update_fields=['status', 'payment_ref', 'updated_at'])

    # In id order, so two orders for the same sizes take their stock rows in
    # the same order and cannot deadlock.
    lines = list(
        order.lines.select_related('order__buyer', 'plan', 'tier__event', 'product_size__product').order_by('id')
    )
    for line in lines:
        _fulfil(line, payment)

    # Plan posting rule: merch order paid -> debit Cash, credit Merchandise
    # revenue, source reference "Order": one entry for the whole order, at
    # the amount actually paid (after member discount).
    merch_paid = sum(line.amount for line in lines if line.kind == OrderLine.Kind.MERCH)
    if merch_paid:
        post_entry(
            description=f'Merchandise order #{order.pk}',
            source_type=LedgerEntry.SourceType.ORDER,
            source_id=order.pk,
            kind=LedgerEntry.Kind.MERCH_SALE,
            created_by=order.buyer,
            lines=[(CASH, merch_paid, 0), (MERCH_REVENUE, 0, merch_paid)],
        )
    return payment


def _fulfil(line, payment):
    """Deliver what a paid line bought (and, for memberships and tickets,
    post its ledger entry; merch is posted once per order by the caller).
    """
    if line.kind == OrderLine.Kind.TICKET:
        issue_tickets(line, payment)
        return
    if line.kind == OrderLine.Kind.MERCH:
        take_stock(line)
        return

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


def _result(order, payment, lines, replayed=False):
    return PurchaseResult(
        order=order, payment=payment,
        membership=next((line.membership for line in lines if line.membership_id), None),
        tickets=list(order.tickets.select_related('event', 'tier').order_by('id')),
        replayed=replayed,
    )


def _replay(user, idempotency_key, same_purchase):
    """If this key already paid for exactly this purchase, return that first
    result. None if the key is unused.

    same_purchase(lines) says whether an existing order's lines are what the
    current request is asking for.
    """
    payment = Payment.objects.select_related('order').filter(idempotency_key=idempotency_key).first()
    if payment is None:
        return None
    order = payment.order
    lines = list(order.lines.select_related('membership__plan'))
    if order.buyer_id != user.pk or not same_purchase(lines):
        # Never hand one user's order to another, or pretend a different
        # purchase was made.
        raise IdempotencyConflict()
    return _result(order, payment, lines, replayed=True)


def create_order(user, line_fields, **order_fields):
    """A pending order with its lines. Amounts come from the lines, which
    the server priced; nothing here is taken from the client.
    """
    subtotal = sum(fields['qty'] * fields['unit_price'] for fields in line_fields)
    discount = sum(fields.get('discount', 0) for fields in line_fields)
    order = Order.objects.create(
        buyer=user, subtotal=subtotal, discount=discount, total=subtotal - discount, **order_fields,
    )
    for fields in line_fields:
        OrderLine.objects.create(order=order, **fields)
    return order


def _purchase(*, user, idempotency_key, outcome, same_purchase, build_lines):
    """Shared purchase skeleton: lock, replay check, order, payment.

    build_lines() runs inside the transaction after the buyer is locked. It
    returns the fields of each order line to create (and may take further
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

            replay = _replay(user, idempotency_key, same_purchase)
            if replay is not None:
                return replay

            if Order.objects.filter(idempotency_key=idempotency_key).exists():
                # The key belongs to a Razorpay checkout. Its Payment row
                # will be written with this key when that payment is
                # verified, so it cannot also pay for this purchase.
                raise IdempotencyConflict()

            order = create_order(user, build_lines())
            payment = process_payment(order, outcome, idempotency_key)
            return _result(order, payment, list(order.lines.select_related('membership__plan')))
    except IntegrityError:
        # Two different users sent the same key at the same moment: the
        # unique constraint stopped the second, and everything it had done
        # was rolled back. _replay now sees the winner's payment and raises
        # IdempotencyConflict. If the key is still unused, the IntegrityError
        # was about something else and is re-raised.
        replay = _replay(user, idempotency_key, same_purchase)
        if replay is not None:
            return replay
        raise


def _single_line(**wanted):
    """Replay matcher for purchases that are exactly one order line."""
    def same_purchase(lines):
        return len(lines) == 1 and all(getattr(lines[0], name) == value for name, value in wanted.items())
    return same_purchase


# What is being bought ------------------------------------------------------
#
# Each *_basket function describes one purchase as {same_purchase,
# build_lines}: the replay matcher and the function that validates the sale
# and prices its lines. Both gateways use the same basket, so the sales
# window, stock, seats and prices are checked by the same code whichever
# way the buyer pays.

def membership_basket(*, user, plan):
    """The price comes from the plan row; nothing the client sends affects it."""
    kind = OrderLine.Kind.MEMBERSHIP
    return {
        'same_purchase': _single_line(kind=kind, plan_id=plan.pk),
        'build_lines': lambda: [{'kind': kind, 'plan': plan, 'qty': 1, 'unit_price': plan.price}],
    }


def purchase_membership(*, user, plan, outcome, idempotency_key):
    """Buy or renew a plan: order, payment, membership and ledger entry."""
    return _purchase(
        user=user, idempotency_key=idempotency_key, outcome=outcome, **membership_basket(user=user, plan=plan),
    )


def ticket_price(tier, user):
    """Team decision: member_price if the buyer has an active membership at
    purchase time, otherwise public_price. No stacking with plan discounts.
    """
    return tier.member_price if membership_status(user) == 'active' else tier.public_price


def tickets_basket(*, user, tier_id, quantity):
    """Seats in one tier.

    Plan, overselling seats: "In one transaction: lock the ticket tier row,
    check sold_count < capacity, create tickets, increment sold_count."
    Raises SoldOut or SalesClosed before anything is written.
    """
    kind = OrderLine.Kind.TICKET

    def build_lines():
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
        return [{'kind': kind, 'tier': tier, 'qty': quantity, 'unit_price': ticket_price(tier, user)}]

    return {
        'same_purchase': _single_line(kind=kind, tier_id=tier_id, qty=quantity),
        'build_lines': build_lines,
    }


def purchase_tickets(*, user, tier_id, quantity, outcome, idempotency_key):
    """Buy seats in one tier: order, payment, tickets and ledger entry."""
    return _purchase(
        user=user, idempotency_key=idempotency_key, outcome=outcome,
        **tickets_basket(user=user, tier_id=tier_id, quantity=quantity),
    )


def merch_discount_pct(user):
    """Team decision: merch uses the plan's merch_discount_pct, for a buyer
    whose membership is active at purchase time. 0 for everyone else.
    """
    membership = current_membership(user)
    return membership.plan.merch_discount_pct if membership else 0


def merch_line_discount(base_price, quantity, pct):
    """Discount for one line, in whole paise.
    ASSUMPTION (plan is silent on rounding): rounded down, so a fraction of
    a paisa is never given away.
    """
    return base_price * quantity * pct // 100


class ProductUnavailable(Exception):
    """A requested size does not exist or its product is not active."""


def merch_basket(*, user, items):
    """Merchandise, one line per size. items is {product_size_id: quantity}.
    Raises OutOfStock or ProductUnavailable before anything is written.
    """
    kind = OrderLine.Kind.MERCH
    wanted = sorted(items.items())

    def same_purchase(lines):
        return (
            all(line.kind == kind for line in lines)
            and sorted((line.product_size_id, line.qty) for line in lines) == wanted
        )

    def build_lines():
        # Row locks on every size in the order, always taken in id order so
        # two orders for the same sizes cannot deadlock. A second buyer of
        # the last hoodie waits here and then reads the reduced stock.
        sizes = {
            size.pk: size
            for size in ProductSize.objects.select_for_update(of=('self',))
            .select_related('product').filter(pk__in=items).order_by('pk')
        }
        pct = merch_discount_pct(user)
        lines = []
        for size_id, quantity in wanted:
            size = sizes.get(size_id)
            if size is None or not size.product.active:
                raise ProductUnavailable()
            if size.stock < quantity:
                raise OutOfStock(size)
            price = size.product.base_price
            lines.append({
                'kind': kind, 'product_size': size, 'qty': quantity, 'unit_price': price,
                'discount': merch_line_discount(price, quantity, pct),
            })
        return lines

    return {'same_purchase': same_purchase, 'build_lines': build_lines}


def purchase_merch(*, user, items, outcome, idempotency_key):
    """Buy merchandise: order, payment, stock decrement with
    StockMovements, and one ledger entry for the order.
    """
    return _purchase(
        user=user, idempotency_key=idempotency_key, outcome=outcome, **merch_basket(user=user, items=items),
    )
