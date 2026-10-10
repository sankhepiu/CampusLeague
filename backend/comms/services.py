"""Publishing announcements and delivering them by email.

Plan: "Saving an announcement creates one delivery row per recipient (status
queued). A sender processes the queue, marks each row sent or failed with
the error, and retries failures a few times."
"""
import logging

from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from .models import Announcement, AnnouncementDelivery

logger = logging.getLogger('campusleague.comms')
User = get_user_model()

# "Retries failures a few times": a delivery is attempted at most this often.
MAX_ATTEMPTS = 3

QUEUED = AnnouncementDelivery.Status.QUEUED
SENT = AnnouncementDelivery.Status.SENT
FAILED = AnnouncementDelivery.Status.FAILED


def recipients_for(audience):
    users = User.objects.filter(is_active=True)
    if audience == Announcement.Audience.MEMBERS:
        today = timezone.localdate()
        users = users.filter(
            memberships__status='active', memberships__start_date__lte=today, memberships__end_date__gte=today,
        ).distinct()
    return users


@transaction.atomic
def publish(*, author, title, body, audience=Announcement.Audience.ALL):
    """Save the announcement and queue one delivery per recipient.

    Nothing is emailed here. This commits first, so the announcement is on
    record whatever happens to the email afterwards.
    """
    announcement = Announcement.objects.create(author=author, title=title, body=body, audience=audience)
    AnnouncementDelivery.objects.bulk_create(
        AnnouncementDelivery(announcement=announcement, recipient=user)
        for user in recipients_for(audience)
    )
    return announcement


def email_delivery(delivery):
    announcement = delivery.announcement
    send_mail(
        subject=announcement.title,
        message=f'{announcement.body}\n\nPosted by {announcement.author.name}',
        from_email=None,
        recipient_list=[delivery.recipient.email],
    )


def send_pending(announcement=None, send=email_delivery):
    """One pass over the queue: try every delivery that is queued, or failed
    with attempts left. Each row is saved as soon as its result is known, so
    one bad address cannot undo the others.

    Call it again (or run `manage.py send_announcements`) to retry failures.
    """
    pending = (
        AnnouncementDelivery.objects
        .filter(status__in=[QUEUED, FAILED], attempts__lt=MAX_ATTEMPTS)
        .select_related('announcement__author', 'recipient')
    )
    if announcement is not None:
        pending = pending.filter(announcement=announcement)

    sent = failed = 0
    for delivery in pending:
        delivery.attempts += 1
        try:
            send(delivery)
        except Exception as exc:
            logger.warning('Announcement %s to user %s failed: %s', delivery.announcement_id, delivery.recipient_id, exc)
            delivery.status = FAILED
            # Kept for the delivery log; the type and message, never a traceback.
            delivery.last_error = f'{type(exc).__name__}: {exc}'[:500]
            failed += 1
        else:
            delivery.status = SENT
            delivery.last_error = ''
            sent += 1
        delivery.save(update_fields=['status', 'attempts', 'last_error', 'updated_at'])
    return {'sent': sent, 'failed': failed}


def delivery_summary(announcement):
    counts = dict(
        announcement.deliveries.values_list('status').annotate(total=Count('id')).values_list('status', 'total')
    )
    return {
        'recipients': sum(counts.values()),
        'queued': counts.get(QUEUED, 0), 'sent': counts.get(SENT, 0), 'failed': counts.get(FAILED, 0),
    }
