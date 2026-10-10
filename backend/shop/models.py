from django.conf import settings
from django.db import models

from common.models import TimeStampedModel


class Order(TimeStampedModel):
    """Plan, data model: "Order: buyer FK, status, subtotal, discount, total,
    payment_ref". One purchase flow serves membership, tickets and merch.
    All amounts are paise.
    """

    class Status(models.TextChoices):
        PENDING = 'pending'
        PAID = 'paid'
        CANCELLED = 'cancelled'

    buyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='orders')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    subtotal = models.BigIntegerField()
    discount = models.BigIntegerField(default=0)
    total = models.BigIntegerField()
    # The gateway's reference for the successful payment; empty until paid.
    payment_ref = models.CharField(max_length=64, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(subtotal__gte=0, discount__gte=0, total__gte=0),
                name='order_amounts_not_negative',
            ),
            # The three amounts are stored as the plan lists them, so the
            # database guarantees they can never disagree.
            models.CheckConstraint(
                condition=models.Q(total=models.F('subtotal') - models.F('discount')),
                name='order_total_is_subtotal_minus_discount',
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=['pending', 'paid', 'cancelled']),
                name='order_status_is_known',
            ),
        ]

    def __str__(self):
        return f'Order #{self.pk} ({self.status})'


class OrderLine(TimeStampedModel):
    """Plan, data model: "OrderLine: order FK, kind (merch, ticket,
    membership), product_size FK or tier FK or plan FK, qty, unit_price".

    Only plan exists so far; product_size and tier arrive with their phases.
    """

    class Kind(models.TextChoices):
        MERCH = 'merch'
        TICKET = 'ticket'
        MEMBERSHIP = 'membership'

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='lines')
    kind = models.CharField(max_length=10, choices=Kind.choices)
    plan = models.ForeignKey(
        'members.MembershipPlan', null=True, blank=True, on_delete=models.PROTECT, related_name='+',
    )
    qty = models.PositiveIntegerField(default=1)
    # Price per unit actually charged, calculated on the server.
    unit_price = models.BigIntegerField()
    # ADDITION to the plan's field list: the membership this line paid for.
    # Needed so an idempotent replay can return the first result, and so the
    # ledger can later be traced from payment to membership. One-to-one: a
    # paid line can never produce two memberships.
    membership = models.OneToOneField(
        'members.Membership', null=True, blank=True, on_delete=models.PROTECT, related_name='order_line',
    )

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(qty__gte=1), name='order_line_qty_at_least_one'),
            models.CheckConstraint(
                condition=models.Q(unit_price__gte=0), name='order_line_unit_price_not_negative',
            ),
            models.CheckConstraint(
                condition=~models.Q(kind='membership') | models.Q(plan__isnull=False),
                name='order_line_membership_has_plan',
            ),
        ]

    @property
    def amount(self):
        return self.qty * self.unit_price

    def __str__(self):
        return f'{self.kind} x{self.qty} on order #{self.order_id}'


class Payment(TimeStampedModel):
    """Plan, data model: "Payment: order FK, amount, status, idempotency_key
    (unique), gateway_ref. Mock gateway writes here."

    Team decision: a row exists only for a successful charge. A failed or
    pending attempt creates no Payment.
    """

    class Status(models.TextChoices):
        SUCCEEDED = 'succeeded'

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name='payments')
    amount = models.BigIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SUCCEEDED)
    # Chosen by the client, one per purchase attempt. UNIQUE is what makes a
    # repeated request unable to charge twice.
    idempotency_key = models.CharField(max_length=64, unique=True)
    gateway_ref = models.CharField(max_length=64)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name='payment_amount_positive'),
            # An order can be paid for once.
            models.UniqueConstraint(
                fields=['order'], condition=models.Q(status='succeeded'),
                name='payment_one_success_per_order',
            ),
        ]

    def __str__(self):
        return f'Payment #{self.pk} for order #{self.order_id}'
