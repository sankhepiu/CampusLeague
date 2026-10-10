from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from finance.models import LedgerEntry, LedgerLine
from finance.services import post_entry

from .models import FundraiserSale, Task

CASH = '1000'
FUNDRAISER_REVENUE = '4300'


@transaction.atomic
def record_sale(*, fundraiser, amount, recorded_by, note=''):
    """Record money a fundraiser took in, with its ledger entry. Plan
    posting rule: debit Cash, credit Fundraiser revenue, source "Fundraiser
    sale record".
    """
    sale = FundraiserSale.objects.create(fundraiser=fundraiser, amount=amount, recorded_by=recorded_by, note=note)
    post_entry(
        description=f'{fundraiser.title}: {note or "sale"}'[:255],
        source_type=LedgerEntry.SourceType.FUNDRAISER_SALE,
        source_id=sale.pk,
        kind=LedgerEntry.Kind.FUNDRAISER_SALE,
        created_by=recorded_by,
        lines=[(CASH, amount, 0), (FUNDRAISER_REVENUE, 0, amount)],
    )
    return sale


def raised_amount(fundraiser):
    """Plan: "Raised amount computed from ledger". Sums the Fundraiser
    revenue lines of the entries posted for this fundraiser's sales; there is
    no stored total to drift out of date.
    """
    sale_ids = fundraiser.sales.values_list('pk', flat=True)
    totals = LedgerLine.objects.filter(
        account__code=FUNDRAISER_REVENUE,
        entry__source_type=LedgerEntry.SourceType.FUNDRAISER_SALE,
        entry__source_id__in=sale_ids,
    ).aggregate(credit=Sum('credit', default=0), debit=Sum('debit', default=0))
    return totals['credit'] - totals['debit']


def progress(fundraiser, today=None):
    """Plan: "Raised amount from the ledger, tasks done vs total, on-track
    flag against goal and time."
    """
    today = today or timezone.localdate()
    raised = raised_amount(fundraiser)
    total_days = (fundraiser.ends_on - fundraiser.starts_on).days + 1
    elapsed = min(max((today - fundraiser.starts_on).days + 1, 0), total_days)
    # ASSUMPTION (plan does not define "on track"): the share of the goal
    # raised is at least the share of the time that has passed.
    on_track = raised * total_days >= fundraiser.goal_amount * elapsed
    tasks = fundraiser.tasks.all()
    return {
        'goal_amount': fundraiser.goal_amount,
        'raised_amount': raised,
        'raised_pct': min(round(raised * 100 / fundraiser.goal_amount, 1), 100.0),
        'tasks_total': tasks.count(),
        'tasks_done': tasks.filter(status=Task.Status.DONE).count(),
        'on_track': on_track,
    }
