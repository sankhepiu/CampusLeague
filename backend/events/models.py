from django.conf import settings
from django.db import models

from common.models import TimeStampedModel


class Event(TimeStampedModel):
    """Plan, data model: "Event: title, description, venue, starts_at,
    ends_at, capacity_total, status (draft, on_sale, closed), budget_amount".
    """

    class Status(models.TextChoices):
        DRAFT = 'draft'
        ON_SALE = 'on_sale'
        CLOSED = 'closed'

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    venue = models.CharField(max_length=200)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    # Team decision: the tiers' capacities may not add up to more than this.
    capacity_total = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    # Paise. Feeds event P&L.
    budget_amount = models.BigIntegerField(default=0)
    # ADDITION to the plan's field list: who created the event, shown as its
    # organiser. Empty for events made before this field existed.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='+',
    )

    class Meta:
        ordering = ['starts_at', 'id']
        constraints = [
            models.CheckConstraint(condition=models.Q(ends_at__gt=models.F('starts_at')), name='event_ends_after_start'),
            models.CheckConstraint(condition=models.Q(capacity_total__gte=1), name='event_capacity_at_least_one'),
            models.CheckConstraint(condition=models.Q(budget_amount__gte=0), name='event_budget_not_negative'),
            models.CheckConstraint(
                condition=models.Q(status__in=['draft', 'on_sale', 'closed']), name='event_status_is_known',
            ),
        ]

    def __str__(self):
        return self.title


class TicketTier(TimeStampedModel):
    """Plan, data model: "TicketTier: event FK, name, public_price,
    member_price, capacity, sold_count, sale_opens, sale_closes. Capacity per
    tier; sold_count changed only inside the purchase transaction."
    """

    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name='tiers')
    name = models.CharField(max_length=100)
    # Paise. Team decision: a buyer with an active membership at purchase
    # time pays member_price; everyone else pays public_price.
    public_price = models.BigIntegerField()
    member_price = models.BigIntegerField()
    capacity = models.PositiveIntegerField()
    sold_count = models.PositiveIntegerField(default=0)
    # ASSUMPTION (plan lists the fields without rules): both are optional;
    # empty means no limit on that side.
    sale_opens = models.DateTimeField(null=True, blank=True)
    sale_closes = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['public_price', 'id']
        constraints = [
            # Plan: "Add a database check so sold_count can never exceed
            # capacity." The last line of defence against overselling.
            models.CheckConstraint(
                condition=models.Q(sold_count__lte=models.F('capacity')), name='tier_sold_not_over_capacity',
            ),
            models.CheckConstraint(condition=models.Q(capacity__gte=1), name='tier_capacity_at_least_one'),
            # ASSUMPTION (plan is silent): no free tickets yet, so every
            # ticket has a payment and a ledger entry behind it.
            models.CheckConstraint(
                condition=models.Q(public_price__gt=0, member_price__gt=0), name='tier_prices_positive',
            ),
            models.UniqueConstraint(fields=['event', 'name'], name='tier_name_unique_per_event'),
        ]

    @property
    def seats_left(self):
        return self.capacity - self.sold_count

    def sale_is_open(self, now):
        """The event is on sale and now is inside this tier's sale window.
        Says nothing about seats: a sold-out tier can still be "open".
        """
        return (
            self.event.status == Event.Status.ON_SALE
            and not (self.sale_opens and now < self.sale_opens)
            and not (self.sale_closes and now >= self.sale_closes)
        )

    def __str__(self):
        return f'{self.event}: {self.name}'


class TicketPass(TimeStampedModel):
    """ASSUMPTION (beyond the plan): one QR code for all the tickets bought
    together. An order of N seats in a tier still creates N Ticket rows, so
    seat counting is unchanged; the pass groups them and carries one signed
    token. Each scan of the pass admits the next ticket not yet used.

    There is no "admitted" counter here on purpose: it is counted from the
    tickets, so it cannot disagree with them.
    """

    order = models.ForeignKey('shop.Order', on_delete=models.PROTECT, related_name='ticket_passes')
    tier = models.ForeignKey(TicketTier, on_delete=models.PROTECT, related_name='passes')
    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name='passes')
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='ticket_passes')
    # Signed token shown as the QR code. See events.tickets.sign_pass.
    qr_token = models.CharField(max_length=255)

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [
            models.UniqueConstraint(fields=['order', 'tier'], name='ticket_pass_one_per_order_and_tier'),
        ]

    def __str__(self):
        return f'Pass #{self.pk} ({self.tier})'


class Ticket(TimeStampedModel):
    """Plan, data model: "Ticket: event FK, tier FK, owner FK, order FK, code
    (unique), qr_token, status (valid, checked_in, cancelled), price_paid.
    One row per seat."
    """

    class Status(models.TextChoices):
        VALID = 'valid'
        CHECKED_IN = 'checked_in'
        CANCELLED = 'cancelled'

    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name='tickets')
    tier = models.ForeignKey(TicketTier, on_delete=models.PROTECT, related_name='tickets')
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='tickets')
    order = models.ForeignKey('shop.Order', on_delete=models.PROTECT, related_name='tickets')
    # The group pass this seat belongs to. Every ticket has one; nullable
    # only so the column could be added to a table that already had rows.
    ticket_pass = models.ForeignKey(
        TicketPass, null=True, blank=True, on_delete=models.PROTECT, related_name='tickets',
    )
    # Short code for typing in when the camera scanner fails.
    code = models.CharField(max_length=12, unique=True)
    # Signed token shown as the QR code. See events.tickets.sign_ticket.
    qr_token = models.CharField(max_length=255)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.VALID)
    price_paid = models.BigIntegerField()

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=['valid', 'checked_in', 'cancelled']), name='ticket_status_is_known',
            ),
            models.CheckConstraint(condition=models.Q(price_paid__gte=0), name='ticket_price_paid_not_negative'),
        ]

    def __str__(self):
        return f'{self.code} ({self.status})'


class CheckIn(TimeStampedModel):
    """Plan, data model: "CheckIn: ticket FK (unique), scanned_by FK,
    scanned_at, member_status_at_scan. Unique per ticket stops double scans."
    """

    # OneToOne is a foreign key with a UNIQUE constraint: the database
    # itself refuses a second check-in for the same ticket.
    ticket = models.OneToOneField(Ticket, on_delete=models.PROTECT, related_name='checkin')
    scanned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    scanned_at = models.DateTimeField()
    # active, lapsed or none, as it was at the door.
    member_status_at_scan = models.CharField(max_length=10)

    def __str__(self):
        return f'Check-in of {self.ticket_id} at {self.scanned_at}'
