"""Figures computed from ledger lines. Nothing here is stored."""
from django.db.models import Sum

from events.models import CheckIn, Ticket

from .models import LedgerAccount, LedgerLine

REVENUE = LedgerAccount.Type.REVENUE
EXPENSE = LedgerAccount.Type.EXPENSE


def event_attendance(event):
    """Sold, checked in and no-shows (R10), overall and per tier."""
    tiers = []
    for tier in event.tiers.all():
        sold = Ticket.objects.filter(tier=tier).exclude(status=Ticket.Status.CANCELLED).count()
        checked_in = CheckIn.objects.filter(ticket__tier=tier).count()
        tiers.append({
            'id': tier.id, 'name': tier.name, 'capacity': tier.capacity,
            'sold': sold, 'checked_in': checked_in, 'no_shows': sold - checked_in,
        })
    sold = sum(tier['sold'] for tier in tiers)
    checked_in = sum(tier['checked_in'] for tier in tiers)
    return {
        'capacity_total': event.capacity_total,
        'sold': sold,
        'checked_in': checked_in,
        # ASSUMPTION: a no-show is a sold ticket not (yet) checked in; the
        # number is only meaningful once the event is over.
        'no_shows': sold - checked_in,
        'attendance_rate_pct': round(checked_in * 100 / sold, 1) if sold else None,
        'tiers': tiers,
    }


def event_pnl(event):
    """Plan: "How much did the gala make? Revenue minus expenses where the
    event matches." Reversal entries carry the same event tag, so they net
    out here without special handling.
    """
    rows = (
        LedgerLine.objects.filter(entry__event=event)
        .values('account__code', 'account__name', 'account__type')
        .annotate(debit=Sum('debit'), credit=Sum('credit'))
        .order_by('account__code')
    )
    revenue, expenses = [], []
    for row in rows:
        account = {'code': row['account__code'], 'name': row['account__name']}
        if row['account__type'] == REVENUE:
            revenue.append({**account, 'amount': row['credit'] - row['debit']})
        elif row['account__type'] == EXPENSE:
            expenses.append({**account, 'amount': row['debit'] - row['credit']})
    revenue_total = sum(item['amount'] for item in revenue)
    expense_total = sum(item['amount'] for item in expenses)
    return {
        'revenue': {'total': revenue_total, 'by_account': revenue},
        'expenses': {'total': expense_total, 'by_account': expenses},
        'profit': revenue_total - expense_total,
        # Budget vs actual: the event's planned spend against real expenses.
        'budget': {
            'amount': event.budget_amount,
            'spent': expense_total,
            'remaining': event.budget_amount - expense_total,
        },
    }
