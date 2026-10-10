from datetime import timedelta

from django.utils import timezone

from events.models import Event, TicketTier
from members.models import Membership, MembershipPlan


def make_event(**overrides):
    now = timezone.now()
    fields = {
        'title': 'Spring Gala', 'venue': 'Main Hall', 'capacity_total': 100, 'status': 'on_sale',
        'starts_at': now + timedelta(days=30), 'ends_at': now + timedelta(days=30, hours=4),
    }
    fields.update(overrides)
    return Event.objects.create(**fields)


def make_tier(event, **overrides):
    fields = {'name': 'General', 'public_price': 80000, 'member_price': 60000, 'capacity': 10}
    fields.update(overrides)
    return TicketTier.objects.create(event=event, **fields)


def make_member(user, days_left=100):
    """Give user a membership ending days_left days from today (negative =
    already ended)."""
    plan, _ = MembershipPlan.objects.get_or_create(
        name='Basic', defaults={'price': 50000, 'duration_months': 12},
    )
    end = timezone.localdate() + timedelta(days=days_left)
    return Membership.objects.create(
        user=user, plan=plan, status='active', start_date=end - timedelta(days=365), end_date=end,
    )
