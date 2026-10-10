from django.db import models


class TimeStampedModel(models.Model):
    """Plan, data model: "Every table has id, created_at, updated_at"."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Abstract: no table of its own; the columns are copied into each
        # model that inherits from it.
        abstract = True
