import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from common.models import TimeStampedModel


class LedgerAccount(TimeStampedModel):
    """Plan, ledger design: the chart of accounts. The starter list (1000 to
    5200) is created by migration 0002.
    """

    class Type(models.TextChoices):
        ASSET = 'asset'
        REVENUE = 'revenue'
        EXPENSE = 'expense'
        LIABILITY = 'liability'

    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=10, choices=Type.choices)

    def __str__(self):
        return f'{self.code} {self.name}'


class LedgerEntry(TimeStampedModel):
    """One financial event. Plan: "one entry per source record", "never
    update or delete a ledger entry".

    Rows are append-only: database triggers (migration 0002) refuse UPDATE
    and DELETE, and refuse to commit an entry whose debits and credits differ.
    Create entries only through finance.services.post_entry.
    """

    class SourceType(models.TextChoices):
        PAYMENT = 'payment'
        ORDER_LINE = 'order_line'
        ORDER = 'order'
        EXPENSE_REQUEST = 'expense_request'
        FUNDRAISER_SALE = 'fundraiser_sale'

    class Kind(models.TextChoices):
        MEMBERSHIP_DUES = 'membership_dues'
        TICKET_SALE = 'ticket_sale'
        MERCH_SALE = 'merch_sale'
        EXPENSE_APPROVED = 'expense_approved'
        EXPENSE_PAID = 'expense_paid'
        FUNDRAISER_SALE = 'fundraiser_sale'

    posted_at = models.DateTimeField(default=timezone.now)
    description = models.CharField(max_length=255)
    # The record that caused this entry. A plain type + id pair, as the plan
    # lists it, because sources live in several different tables.
    source_type = models.CharField(max_length=30, choices=SourceType.choices)
    source_id = models.PositiveBigIntegerField()
    # Listed in the plan's unique constraint but not in its field list; added
    # because one source can post more than once (an expense: approved, then
    # paid).
    kind = models.CharField(max_length=30, choices=Kind.choices)
    # Plan: "tagged with the event where relevant". This is what lets event
    # profit be computed straight from the ledger.
    event = models.ForeignKey(
        'events.Event', null=True, blank=True, on_delete=models.PROTECT, related_name='ledger_entries',
    )
    # One-to-one: an entry can be reversed at most once.
    reverses = models.OneToOneField(
        'self', null=True, blank=True, on_delete=models.PROTECT, related_name='reversed_by',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='+',
    )

    class Meta:
        constraints = [
            # Plan: "Unique on (source_type, source_id, kind) to stop double
            # posting". A retry that reaches the ledger twice fails here.
            models.UniqueConstraint(
                fields=['source_type', 'source_id', 'kind'],
                name='ledger_one_entry_per_source',
            ),
        ]

    def __str__(self):
        return f'#{self.pk} {self.kind} ({self.source_type} {self.source_id})'


class LedgerLine(TimeStampedModel):
    """One side of an entry: a debit or a credit to one account, in paise."""

    entry = models.ForeignKey(LedgerEntry, on_delete=models.PROTECT, related_name='lines')
    account = models.ForeignKey(LedgerAccount, on_delete=models.PROTECT, related_name='lines')
    debit = models.BigIntegerField(default=0)
    credit = models.BigIntegerField(default=0)

    class Meta:
        constraints = [
            # Exactly one side is a positive amount. Rules out negative
            # amounts, zero lines, and a line that is both debit and credit.
            models.CheckConstraint(
                condition=(
                    models.Q(debit__gt=0, credit=0) | models.Q(debit=0, credit__gt=0)
                ),
                name='ledger_line_one_positive_side',
            ),
        ]

    def __str__(self):
        side = f'Dr {self.debit}' if self.debit else f'Cr {self.credit}'
        return f'{self.account.code} {side}'


def receipt_path(instance, filename):
    # The uploader's file name is never used: a random name cannot collide,
    # be guessed, or smuggle in a path. The extension is validated before
    # this runs.
    extension = filename.rsplit('.', 1)[-1].lower()
    return f'receipts/{uuid.uuid4().hex}.{extension}'


class ExpenseRequest(TimeStampedModel):
    """Plan, data model: "ExpenseRequest: requester FK, amount, category,
    event FK (optional), fundraiser FK (optional), description, receipt_file,
    status (submitted, approved, rejected, paid)".

    status changes only in finance.expenses (approve, reject, mark_paid),
    which also posts the ledger entry in the same transaction.
    """

    class Status(models.TextChoices):
        SUBMITTED = 'submitted'
        APPROVED = 'approved'
        REJECTED = 'rejected'
        PAID = 'paid'

    class Category(models.TextChoices):
        # ASSUMPTION (plan says "expense account (by category)" without
        # listing categories): one per expense account in the starter list.
        EVENT = 'event'              # 5000 Event expenses
        FUNDRAISER = 'fundraiser'    # 5100 Fundraiser expenses
        GENERAL = 'general'          # 5200 General club expenses

    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='expense_requests')
    amount = models.BigIntegerField()
    category = models.CharField(max_length=10, choices=Category.choices)
    event = models.ForeignKey('events.Event', null=True, blank=True, on_delete=models.PROTECT, related_name='expense_requests')
    fundraiser = models.ForeignKey(
        'volunteering.Fundraiser', null=True, blank=True, on_delete=models.PROTECT, related_name='expense_requests',
    )
    description = models.CharField(max_length=500)
    receipt_file = models.FileField(upload_to=receipt_path, max_length=200)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SUBMITTED)

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name='expense_amount_positive'),
            models.CheckConstraint(
                condition=models.Q(status__in=['submitted', 'approved', 'rejected', 'paid']),
                name='expense_status_is_known',
            ),
            # The category decides which tag is required, so an expense can
            # always be attributed for event and fundraiser P&L.
            models.CheckConstraint(
                condition=(
                    models.Q(category='event', event__isnull=False, fundraiser__isnull=True)
                    | models.Q(category='fundraiser', fundraiser__isnull=False, event__isnull=True)
                    | models.Q(category='general', event__isnull=True, fundraiser__isnull=True)
                ),
                name='expense_category_matches_its_tag',
            ),
        ]

    def __str__(self):
        return f'Expense #{self.pk} ({self.status})'


class Approval(TimeStampedModel):
    """Plan, data model: "Approval: expense FK, approver FK, decision,
    reason, decided_at. Approver must differ from requester."
    """

    class Decision(models.TextChoices):
        APPROVED = 'approved'
        REJECTED = 'rejected'

    # One-to-one: a request is decided exactly once.
    expense = models.OneToOneField(ExpenseRequest, on_delete=models.PROTECT, related_name='approval')
    approver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    decision = models.CharField(max_length=10, choices=Decision.choices)
    reason = models.CharField(max_length=500, blank=True)
    decided_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(decision__in=['approved', 'rejected']), name='approval_decision_is_known',
            ),
        ]
