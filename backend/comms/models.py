from django.conf import settings
from django.db import models
from django.utils import timezone

from common.models import TimeStampedModel


class Announcement(TimeStampedModel):
    """Plan, data model: "Announcement: title, body, author FK, published_at,
    audience. Saved before sending."

    The archive (R12: what was said, when, and by whom) reads these rows, so
    it is complete even if every email fails.
    """

    class Audience(models.TextChoices):
        # ASSUMPTION (plan lists "audience" without values).
        ALL = 'all'            # every active account
        MEMBERS = 'members'    # accounts with a membership covering today

    title = models.CharField(max_length=200)
    body = models.TextField()
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='announcements')
    published_at = models.DateTimeField(default=timezone.now)
    audience = models.CharField(max_length=10, choices=Audience.choices, default=Audience.ALL)

    class Meta:
        ordering = ['-published_at', '-id']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(audience__in=['all', 'members']), name='announcement_audience_is_known',
            ),
        ]

    def __str__(self):
        return self.title


class AnnouncementDelivery(TimeStampedModel):
    """Plan, data model: "AnnouncementDelivery: announcement FK, recipient
    FK, status (queued, sent, failed), attempts, last_error. Gives the 'what
    was said, when' record and enables retry."
    """

    class Status(models.TextChoices):
        QUEUED = 'queued'
        SENT = 'sent'
        FAILED = 'failed'

    announcement = models.ForeignKey(Announcement, on_delete=models.PROTECT, related_name='deliveries')
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ['id']
        constraints = [
            # One row, and so at most one email, per person per announcement.
            models.UniqueConstraint(fields=['announcement', 'recipient'], name='delivery_once_per_recipient'),
            models.CheckConstraint(
                condition=models.Q(status__in=['queued', 'sent', 'failed']), name='delivery_status_is_known',
            ),
        ]

    def __str__(self):
        return f'{self.announcement_id} -> {self.recipient_id} ({self.status})'
