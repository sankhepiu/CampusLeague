"""The daily membership job (plan: "Renewal reminders").

"A scheduled job runs daily. It finds active memberships whose end date is
within a set window (for example 14 days and 3 days) and whose reminder has
not been sent for that window, sends an email, and records reminder_sent_at.
It also marks memberships as lapsed once the end date passes."
"""
import logging
from datetime import timedelta

from django.core.mail import send_mail
from django.utils import timezone

from .models import Membership
from .services import paid_until

logger = logging.getLogger('campusleague.renewals')

# Days before end_date at which a reminder goes out (the plan's example).
REMINDER_WINDOWS = [14, 3]

ACTIVE = Membership.Status.ACTIVE
LAPSED = Membership.Status.LAPSED


def _window_start(membership, today):
    """First day of the reminder window today falls in, or None."""
    days_left = (membership.end_date - today).days
    due = [window for window in REMINDER_WINDOWS if days_left <= window]
    if not due:
        return None
    return membership.end_date - timedelta(days=min(due))


def run_daily_job(now=None):
    """Lapse expired memberships and send due reminders. Safe to run any
    number of times a day: a reminder is sent once per window.

    now is the single clock for the whole run (tests pass a future time).
    """
    now = now or timezone.now()
    today = timezone.localdate(now)

    lapsed = Membership.objects.filter(status=ACTIVE, end_date__lt=today).update(
        status=LAPSED, updated_at=now,
    )

    sent = failed = 0
    expiring = (
        Membership.objects
        .filter(status=ACTIVE, start_date__lte=today, end_date__gte=today,
                end_date__lte=today + timedelta(days=max(REMINDER_WINDOWS)))
        .select_related('user', 'plan')
    )
    for membership in expiring:
        window_start = _window_start(membership, today)
        last_sent = membership.reminder_sent_at
        if last_sent and timezone.localdate(last_sent) >= window_start:
            continue  # already reminded for this window
        if paid_until(membership.user, today) > membership.end_date:
            continue  # already renewed; nothing to remind about
        try:
            send_mail(
                subject='Your Campus League membership is about to expire',
                message=(
                    f'Hi {membership.user.name},\n\n'
                    f'Your {membership.plan.name} membership ends on '
                    f'{membership.end_date:%d %b %Y}. Renew in the app to keep your benefits.\n'
                ),
                from_email=None,
                recipient_list=[membership.user.email],
            )
        except Exception:
            # One bad address or a mail outage must not stop the rest.
            # reminder_sent_at stays unset, so the next run tries again.
            logger.exception('Renewal reminder failed for membership %s', membership.pk)
            failed += 1
            continue
        membership.reminder_sent_at = now
        membership.save(update_fields=['reminder_sent_at', 'updated_at'])
        sent += 1

    return {'lapsed': lapsed, 'reminders_sent': sent, 'reminders_failed': failed}
