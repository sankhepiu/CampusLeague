from django.db import models

from common.models import TimeStampedModel


class SaveFile(TimeStampedModel):
    """Plan, data model: "SaveFile: event FK, vendors, budget_notes,
    what_worked, what_didnt, checklist. Handover memory."

    What one committee leaves behind for the next about an event.
    """

    # One-to-one: the database allows a single save file per event.
    event = models.OneToOneField('events.Event', on_delete=models.PROTECT, related_name='save_file')
    vendors = models.TextField(blank=True)
    budget_notes = models.TextField(blank=True)
    what_worked = models.TextField(blank=True)
    what_didnt = models.TextField(blank=True)
    # ASSUMPTION (plan says only "checklist"): a list of short text items.
    checklist = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['-updated_at', '-id']

    def __str__(self):
        return f'Save file: {self.event}'
