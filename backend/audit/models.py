from django.conf import settings
from django.db import models
from django.utils import timezone

from common.models import TimeStampedModel


class AuditLog(TimeStampedModel):
    """Plan, data model: "AuditLog: actor FK, action, object_type, object_id,
    before, after, at. Append-only."

    Append-only is enforced by a database trigger (migration 0002). Write
    rows only through audit.services.record.
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='+',
    )
    action = models.CharField(max_length=50)
    object_type = models.CharField(max_length=50)
    object_id = models.PositiveBigIntegerField()
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-at', '-id']

    def __str__(self):
        return f'{self.action} {self.object_type} {self.object_id}'
