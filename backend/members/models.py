from django.conf import settings
from django.db import models

from common.models import TimeStampedModel


class MembershipPlan(TimeStampedModel):
    """Plan, data model: "MembershipPlan: name, price, duration_months,
    ticket_discount_pct, merch_discount_pct, active. Benefits live on the
    plan."
    """

    # ASSUMPTION (plan is silent): plan names are unique.
    name = models.CharField(max_length=100, unique=True)
    # Paise.
    price = models.PositiveIntegerField()
    duration_months = models.PositiveSmallIntegerField()
    # Team decision: tickets use TicketTier.member_price, so
    # ticket_discount_pct is kept as listed but not applied to tickets.
    ticket_discount_pct = models.PositiveSmallIntegerField(default=0)
    merch_discount_pct = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['price', 'id']
        constraints = [
            # ASSUMPTION (plan is silent): no free plans, so every membership
            # has a real dues payment and ledger entry behind it.
            models.CheckConstraint(condition=models.Q(price__gt=0), name='plan_price_positive'),
            models.CheckConstraint(
                condition=models.Q(duration_months__gte=1), name='plan_duration_at_least_one_month',
            ),
            models.CheckConstraint(
                condition=models.Q(ticket_discount_pct__lte=100), name='plan_ticket_discount_max_100',
            ),
            models.CheckConstraint(
                condition=models.Q(merch_discount_pct__lte=100), name='plan_merch_discount_max_100',
            ),
        ]

    def __str__(self):
        return self.name


class Membership(TimeStampedModel):
    """Plan, data model: "Membership: user FK, plan FK, status, start_date,
    end_date, reminder_sent_at. Active only while today is between start and
    end."

    A renewal is a new row, so the history of what was paid for stays intact.
    Whether a user is a member today is answered by
    members.services.membership_status, which reads the dates, not just the
    stored status.
    """

    class Status(models.TextChoices):
        PENDING = 'pending'
        ACTIVE = 'active'
        LAPSED = 'lapsed'
        CANCELLED = 'cancelled'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='memberships',
    )
    plan = models.ForeignKey(MembershipPlan, on_delete=models.PROTECT, related_name='memberships')
    status = models.CharField(max_length=10, choices=Status.choices)
    # Both dates are inclusive calendar days.
    start_date = models.DateField()
    end_date = models.DateField()
    # Used by the renewal-reminder job (next step).
    reminder_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F('start_date')),
                name='membership_end_not_before_start',
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=['pending', 'active', 'lapsed', 'cancelled']),
                name='membership_status_is_known',
            ),
        ]

    def __str__(self):
        return f'{self.user} {self.plan} {self.start_date} to {self.end_date} ({self.status})'
