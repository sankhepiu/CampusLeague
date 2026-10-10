from django.conf import settings
from django.db import models

from common.models import TimeStampedModel


class Fundraiser(TimeStampedModel):
    """Plan, data model: "Fundraiser: title, goal_amount, starts_on, ends_on,
    status. Raised amount computed from ledger."
    """

    class Status(models.TextChoices):
        # ASSUMPTION (plan lists "status" without values).
        PLANNED = 'planned'
        ACTIVE = 'active'
        CLOSED = 'closed'

    title = models.CharField(max_length=200)
    # Paise. There is deliberately no "raised" column: see
    # volunteering.services.raised_amount.
    goal_amount = models.BigIntegerField()
    starts_on = models.DateField()
    ends_on = models.DateField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        ordering = ['-starts_on', '-id']
        constraints = [
            models.CheckConstraint(condition=models.Q(goal_amount__gt=0), name='fundraiser_goal_positive'),
            models.CheckConstraint(
                condition=models.Q(ends_on__gte=models.F('starts_on')), name='fundraiser_ends_not_before_start',
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=['planned', 'active', 'closed']), name='fundraiser_status_is_known',
            ),
        ]

    def __str__(self):
        return self.title


class Task(TimeStampedModel):
    """Plan, data model: "Task: fundraiser FK (or event FK), title,
    description, status (todo, doing, done), due_date".
    """

    class Status(models.TextChoices):
        TODO = 'todo'
        DOING = 'doing'
        DONE = 'done'

    fundraiser = models.ForeignKey(Fundraiser, null=True, blank=True, on_delete=models.PROTECT, related_name='tasks')
    event = models.ForeignKey('events.Event', null=True, blank=True, on_delete=models.PROTECT, related_name='tasks')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.TODO)
    due_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['due_date', 'id']
        constraints = [
            # Exactly one parent: a fundraiser or an event.
            models.CheckConstraint(
                condition=(
                    models.Q(fundraiser__isnull=False, event__isnull=True)
                    | models.Q(fundraiser__isnull=True, event__isnull=False)
                ),
                name='task_has_exactly_one_parent',
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=['todo', 'doing', 'done']), name='task_status_is_known',
            ),
        ]

    def __str__(self):
        return self.title


class TaskAssignment(TimeStampedModel):
    """Plan, data model: "TaskAssignment: task FK, user FK, role_note"."""

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='assignments')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='task_assignments')
    role_note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(fields=['task', 'user'], name='task_assigned_once_per_user'),
        ]


class FundraiserSale(TimeStampedModel):
    """Team decision: the "fundraiser sale record" the plan's posting rules
    name as the source for fundraiser revenue, which its data model omits.
    Each row posts exactly one ledger entry (debit Cash, credit Fundraiser
    revenue).
    """

    fundraiser = models.ForeignKey(Fundraiser, on_delete=models.PROTECT, related_name='sales')
    amount = models.BigIntegerField()
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name='fundraiser_sale_amount_positive'),
        ]
