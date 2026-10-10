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

    class Kind(models.TextChoices):
        MEMBERSHIP_DUES = 'membership_dues'

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
    # The plan's optional event FK is added with the events app (Phase 2).
    #
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
