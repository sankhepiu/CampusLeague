from django.conf import settings
from django.db import models
from django.db.models.functions import Upper

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
    # Also set on an order flagged needs_refund, so the charge can be found.
    payment_ref = models.CharField(max_length=64, blank=True)
    # ADDITIONS for the Razorpay gateway (beyond the plan, which has only
    # the mock). All three stay empty/false on orders paid through the mock.
    #
    # Razorpay's id for this checkout ("order_..."), set once Razorpay has
    # accepted the order.
    razorpay_order_id = models.CharField(max_length=64, blank=True)
    # The Idempotency-Key the checkout was started with. With Razorpay the
    # Payment row appears only at verify time, so the key has to be
    # remembered here until then; it becomes Payment.idempotency_key.
    idempotency_key = models.CharField(max_length=64, blank=True)
    # The buyer was charged but nothing could be delivered (sold out between
    # checkout and payment). Someone has to refund payment_ref by hand.
    needs_refund = models.BooleanField(default=False)
    # ADDITION (beyond the plan): the coupon used, and how much of
    # `discount` came from it. `discount` stays the total of every discount
    # (sale, member and coupon), so total = subtotal - discount still holds.
    coupon = models.ForeignKey('shop.Coupon', null=True, blank=True, on_delete=models.PROTECT, related_name='orders')
    coupon_discount = models.BigIntegerField(default=0)

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
            models.UniqueConstraint(
                fields=['razorpay_order_id'], condition=~models.Q(razorpay_order_id=''),
                name='order_razorpay_order_id_unique',
            ),
            models.UniqueConstraint(
                fields=['idempotency_key'], condition=~models.Q(idempotency_key=''),
                name='order_idempotency_key_unique',
            ),
            # Only an order that delivered nothing can be owed a refund.
            models.CheckConstraint(
                condition=models.Q(needs_refund=False) | models.Q(status='cancelled'),
                name='order_needs_refund_only_when_cancelled',
            ),
            models.CheckConstraint(
                condition=models.Q(coupon_discount__gte=0, coupon_discount__lte=models.F('discount')),
                name='order_coupon_discount_within_discount',
            ),
            models.CheckConstraint(
                condition=models.Q(coupon__isnull=False) | models.Q(coupon_discount=0),
                name='order_coupon_discount_needs_coupon',
            ),
        ]

    def __str__(self):
        return f'Order #{self.pk} ({self.status})'


class OrderLine(TimeStampedModel):
    """Plan, data model: "OrderLine: order FK, kind (merch, ticket,
    membership), product_size FK or tier FK or plan FK, qty, unit_price".

    Exactly which of plan, tier or product_size is set depends on kind.
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
    tier = models.ForeignKey(
        'events.TicketTier', null=True, blank=True, on_delete=models.PROTECT, related_name='+',
    )
    product_size = models.ForeignKey(
        'shop.ProductSize', null=True, blank=True, on_delete=models.PROTECT, related_name='+',
    )
    qty = models.PositiveIntegerField(default=1)
    # Price per unit before any discount, calculated on the server.
    unit_price = models.BigIntegerField()
    # ADDITION to the plan's field list, required by its ledger rule: "record
    # the revenue at the amount actually paid, and keep the discount on the
    # order line for reporting." Total discount for the line, in paise.
    discount = models.BigIntegerField(default=0)
    # The part of `discount` that came from the order's coupon.
    coupon_discount = models.BigIntegerField(default=0)
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
            models.CheckConstraint(
                condition=~models.Q(kind='ticket') | models.Q(tier__isnull=False),
                name='order_line_ticket_has_tier',
            ),
            models.CheckConstraint(
                condition=~models.Q(kind='merch') | models.Q(product_size__isnull=False),
                name='order_line_merch_has_product_size',
            ),
            models.CheckConstraint(
                condition=models.Q(discount__gte=0, discount__lte=models.F('qty') * models.F('unit_price')),
                name='order_line_discount_within_line_total',
            ),
            models.CheckConstraint(
                condition=models.Q(coupon_discount__gte=0, coupon_discount__lte=models.F('discount')),
                name='order_line_coupon_discount_within_discount',
            ),
        ]

    @property
    def amount(self):
        """What was actually paid for this line."""
        return self.qty * self.unit_price - self.discount

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


class Product(TimeStampedModel):
    """Plan, data model: "Product: name, description, base_price, image,
    active. Hoodie, T-shirt."
    """

    class Category(models.TextChoices):
        APPAREL = 'apparel'
        ACCESSORIES = 'accessories'
        STATIONERY = 'stationery'
        DRINKWARE = 'drinkware'

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    # Paise, before any sale or member discount.
    base_price = models.BigIntegerField()
    # Plan: "image". A file under media/products/. FileField, not
    # ImageField, so no image-processing dependency is needed.
    # ASSUMPTION: there is no upload endpoint yet; images are placed by the
    # seed.
    image = models.FileField(upload_to='products/', max_length=200, blank=True)
    active = models.BooleanField(default=True)
    # ADDITIONS (beyond the plan's field list).
    category = models.CharField(max_length=12, choices=Category.choices, default=Category.APPAREL)
    # Percent off base_price for everyone, before any member discount.
    sale_pct = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['name', 'id']
        constraints = [
            # ASSUMPTION: no free merchandise, as with plans and tickets.
            models.CheckConstraint(condition=models.Q(base_price__gt=0), name='product_base_price_positive'),
            models.CheckConstraint(condition=models.Q(sale_pct__lte=90), name='product_sale_pct_max_90'),
            models.CheckConstraint(
                condition=models.Q(category__in=['apparel', 'accessories', 'stationery', 'drinkware']),
                name='product_category_is_known',
            ),
        ]

    def __str__(self):
        return self.name


class ProductSize(TimeStampedModel):
    """Plan, data model: "ProductSize: product FK, size (S, M, L, XL), stock.
    Stock per size, never negative (database check)."

    stock changes only in shop.stock, which writes a StockMovement in the
    same transaction, so stock always equals the sum of its movements.
    """

    class Size(models.TextChoices):
        S = 'S'
        M = 'M'
        L = 'L'
        XL = 'XL'
        # ADDITION: for products that do not come in sizes (a mug, a pin).
        # Such a product has exactly this one row, which holds its stock.
        ONE = 'ONE'

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='sizes')
    size = models.CharField(max_length=3, choices=Size.choices)
    stock = models.IntegerField(default=0)

    class Meta:
        constraints = [
            # The last line of defence against overselling: PostgreSQL
            # refuses any write that would take stock below zero.
            models.CheckConstraint(condition=models.Q(stock__gte=0), name='product_size_stock_not_negative'),
            models.CheckConstraint(
                condition=models.Q(size__in=['S', 'M', 'L', 'XL', 'ONE']), name='product_size_is_known',
            ),
            models.UniqueConstraint(fields=['product', 'size'], name='product_size_unique_per_product'),
        ]

    def __str__(self):
        return f'{self.product} {self.size}'


class StockMovement(TimeStampedModel):
    """Plan, data model: "StockMovement: product_size FK, delta, reason
    (order, restock, adjustment, cancel), order_line FK. Audit trail for
    stock; current stock must equal the sum."
    """

    class Reason(models.TextChoices):
        ORDER = 'order'
        RESTOCK = 'restock'
        ADJUSTMENT = 'adjustment'
        CANCEL = 'cancel'

    product_size = models.ForeignKey(ProductSize, on_delete=models.PROTECT, related_name='movements')
    # Positive adds stock, negative removes it.
    delta = models.IntegerField()
    reason = models.CharField(max_length=10, choices=Reason.choices)
    order_line = models.ForeignKey(
        OrderLine, null=True, blank=True, on_delete=models.PROTECT, related_name='stock_movements',
    )

    class Meta:
        constraints = [
            models.CheckConstraint(condition=~models.Q(delta=0), name='stock_movement_delta_not_zero'),
            models.CheckConstraint(
                condition=models.Q(reason__in=['order', 'restock', 'adjustment', 'cancel']),
                name='stock_movement_reason_is_known',
            ),
            # A sale's movement must point at the line that caused it.
            models.CheckConstraint(
                condition=~models.Q(reason='order') | models.Q(order_line__isnull=False),
                name='stock_movement_order_has_line',
            ),
        ]

    def __str__(self):
        return f'{self.product_size} {self.delta:+d} ({self.reason})'


class Coupon(TimeStampedModel):
    """ASSUMPTION (beyond the plan): a discount code. Kept in its own table
    so it can later belong to a club.

    All amounts are paise. `value` is a percentage for kind "percent" and an
    amount for kind "flat".
    """

    class Kind(models.TextChoices):
        PERCENT = 'percent'
        FLAT = 'flat'

    class AppliesTo(models.TextChoices):
        ALL = 'all'
        MERCH = 'merch'
        TICKETS = 'tickets'
        MEMBERSHIP = 'membership'

    # Always stored in upper case (the CHECK below enforces it), which with
    # UNIQUE makes codes case-insensitive: welcome10 and WELCOME10 are one.
    code = models.CharField(max_length=20, unique=True)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    value = models.BigIntegerField()
    # The order must come to at least this much (after sale and member
    # discounts) for the coupon to apply.
    min_order = models.BigIntegerField(default=0)
    # The most this coupon can take off; empty means no cap.
    max_discount = models.BigIntegerField(null=True, blank=True)
    # Empty means no limit on that side.
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_to = models.DateTimeField(null=True, blank=True)
    # Paid orders in total, and per user. Empty usage_limit means unlimited.
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    per_user_limit = models.PositiveIntegerField(default=1)
    applies_to = models.CharField(max_length=12, choices=AppliesTo.choices, default=AppliesTo.ALL)
    active = models.BooleanField(default=True)
    # Paid orders so far. Changed only in shop.coupons.redeem, under a row
    # lock, in the same transaction as the payment.
    used_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['code']
        constraints = [
            models.CheckConstraint(condition=models.Q(code=Upper('code')), name='coupon_code_is_upper_case'),
            models.CheckConstraint(condition=models.Q(kind__in=['percent', 'flat']), name='coupon_kind_is_known'),
            models.CheckConstraint(
                condition=models.Q(applies_to__in=['all', 'merch', 'tickets', 'membership']),
                name='coupon_applies_to_is_known',
            ),
            models.CheckConstraint(condition=models.Q(value__gte=1), name='coupon_value_positive'),
            models.CheckConstraint(
                condition=~models.Q(kind='percent') | models.Q(value__lte=100), name='coupon_percent_max_100',
            ),
            models.CheckConstraint(condition=models.Q(min_order__gte=0), name='coupon_min_order_not_negative'),
            models.CheckConstraint(
                condition=models.Q(max_discount__isnull=True) | models.Q(max_discount__gte=1),
                name='coupon_max_discount_positive',
            ),
            models.CheckConstraint(condition=models.Q(per_user_limit__gte=1), name='coupon_per_user_limit_positive'),
            models.CheckConstraint(
                condition=models.Q(usage_limit__isnull=True) | models.Q(usage_limit__gte=1),
                name='coupon_usage_limit_positive',
            ),
            # The last line of defence against over-use: PostgreSQL refuses
            # a redemption that would take the count past the limit.
            models.CheckConstraint(
                condition=models.Q(usage_limit__isnull=True) | models.Q(used_count__lte=models.F('usage_limit')),
                name='coupon_used_not_over_limit',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(valid_from__isnull=True) | models.Q(valid_to__isnull=True)
                    | models.Q(valid_to__gt=models.F('valid_from'))
                ),
                name='coupon_valid_to_after_valid_from',
            ),
        ]

    def __str__(self):
        return self.code


class CouponRedemption(TimeStampedModel):
    """One paid order that used a coupon. Written only when the payment
    succeeds; a failed, pending or abandoned order leaves no row.
    """

    coupon = models.ForeignKey(Coupon, on_delete=models.PROTECT, related_name='redemptions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    # One-to-one: an order can redeem its coupon once.
    order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name='coupon_redemption')
    discount = models.BigIntegerField()

    def __str__(self):
        return f'{self.coupon} on order #{self.order_id}'
