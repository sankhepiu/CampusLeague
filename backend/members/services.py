import calendar
from datetime import timedelta

from django.db.models import Case, Exists, OuterRef, Value, When
from django.utils import timezone

from .models import Membership

ACTIVE = Membership.Status.ACTIVE
LAPSED = Membership.Status.LAPSED


def add_months(day, months):
    """day + N calendar months. A day that does not exist in the target
    month is clamped to that month's last day (31 Jan + 1 month = 28/29 Feb).
    """
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return day.replace(year=year, month=month, day=min(day.day, last_day))


def current_membership(user, today=None):
    """The membership covering today, or None."""
    today = today or timezone.localdate()
    return (
        Membership.objects
        .filter(user=user, status=ACTIVE, start_date__lte=today, end_date__gte=today)
        .select_related('plan')
        .order_by('-end_date')
        .first()
    )


def membership_status(user, today=None):
    """'active', 'lapsed' or 'none' (the plan's check-in vocabulary).

    Decided from the dates, so it is correct even before the nightly job has
    marked an expired membership as lapsed.
    """
    today = today or timezone.localdate()
    if current_membership(user, today) is not None:
        return 'active'
    had_one = Membership.objects.filter(
        user=user, status__in=[ACTIVE, LAPSED], end_date__lt=today,
    ).exists()
    return 'lapsed' if had_one else 'none'


def paid_until(user, today=None):
    """Last day covered by paid memberships, counting renewals that have not
    started yet. None if nothing covers today or later.
    """
    today = today or timezone.localdate()
    latest = (
        Membership.objects
        .filter(user=user, status=ACTIVE, end_date__gte=today)
        .order_by('-end_date')
        .first()
    )
    return latest.end_date if latest else None


def start_membership(user, plan, today=None):
    """Create the membership a successful dues payment buys.

    Team decision: end_date = start_date + plan.duration_months.
    ASSUMPTION (plan says "buy or renew" without detail): a renewal starts
    the day after the member's current cover ends, so paying early never
    loses days.
    """
    today = today or timezone.localdate()
    covered_until = paid_until(user, today)
    start = covered_until + timedelta(days=1) if covered_until else today
    return Membership.objects.create(
        user=user,
        plan=plan,
        status=ACTIVE,
        start_date=start,
        end_date=add_months(start, plan.duration_months),
    )


def with_membership_status(users, today=None):
    """Annotate a user queryset with membership_status, using the same rule
    as membership_status() above but in SQL, so a list can be filtered and
    paginated by it without one query per user.
    """
    today = today or timezone.localdate()
    memberships = Membership.objects.filter(user=OuterRef('pk'))
    covers_today = memberships.filter(status=ACTIVE, start_date__lte=today, end_date__gte=today)
    ended = memberships.filter(status__in=[ACTIVE, LAPSED], end_date__lt=today)
    return users.annotate(membership_status=Case(
        When(Exists(covers_today), then=Value('active')),
        When(Exists(ended), then=Value('lapsed')),
        default=Value('none'),
    ))
