"""Club Health. Plan: "A score with each component's contribution so it can
be explained", from "membership growth and renewals, attendance rate,
volunteer participation, cash trend".

Every number is counted fresh from the database; nothing is stored.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.utils import timezone

from events.models import CheckIn, Event, Ticket
from finance.models import LedgerLine
from members.models import Membership
from volunteering.models import Task

User = get_user_model()

# ASSUMPTIONS (the plan names the four components but no numbers): all the
# tuning lives here, in one place.
WEIGHTS = {'membership': 30, 'attendance': 25, 'volunteering': 20, 'money': 25}   # sums to 100
MEMBERSHIP_ACTIVE_SHARE_WEIGHT = 70     # within the membership component...
MEMBERSHIP_RENEWAL_WEIGHT = 30          # ...these two sum to 100
CASH_TREND_DAYS = 30

LABELS = {
    'membership': 'Membership', 'attendance': 'Event attendance',
    'volunteering': 'Volunteering', 'money': 'Money',
}
ACTIVE, LAPSED = Membership.Status.ACTIVE, Membership.Status.LAPSED


def pct(part, whole):
    """Whole-number percentage, halves rounded up, integer arithmetic only."""
    return (part * 200 + whole) // (2 * whole)


def rupees(paise):
    return f'Rs {paise / 100:,.2f}'


def _membership(today):
    ever = set(Membership.objects.filter(status__in=[ACTIVE, LAPSED]).values_list('user_id', flat=True))
    if not ever:
        return None, 'Nobody has joined yet.'
    active = set(Membership.objects.filter(
        status=ACTIVE, start_date__lte=today, end_date__gte=today,
    ).values_list('user_id', flat=True))
    active_share = pct(len(active), len(ever))

    # Renewals: of the people who have had a membership run out, how many
    # hold a current one.
    ended = set(Membership.objects.filter(
        status__in=[ACTIVE, LAPSED], end_date__lt=today,
    ).values_list('user_id', flat=True))
    reason = f'{len(active)} of {len(ever)} people who joined are active members ({active_share}%)'
    if not ended:
        return active_share, f'{reason}; no membership has run out yet, so renewals are not scored.'
    renewed = len(ended & active)
    renewal_rate = pct(renewed, len(ended))
    score = (MEMBERSHIP_ACTIVE_SHARE_WEIGHT * active_share + MEMBERSHIP_RENEWAL_WEIGHT * renewal_rate + 50) // 100
    return score, f'{reason}; {renewed} of {len(ended)} whose membership ran out have renewed ({renewal_rate}%).'


def _attendance(today):
    closed = Event.objects.filter(status=Event.Status.CLOSED)
    sold = Ticket.objects.filter(event__in=closed).exclude(status=Ticket.Status.CANCELLED).count()
    if not sold:
        return None, 'No closed event has sold tickets yet.'
    checked_in = CheckIn.objects.filter(ticket__event__in=closed).count()
    return pct(checked_in, sold), (
        f'{checked_in} of {sold} tickets were checked in across {closed.count()} closed event(s).'
    )


def _volunteering(today):
    total = Task.objects.count()
    if not total:
        return None, 'No tasks have been created yet.'
    done = Task.objects.filter(status=Task.Status.DONE).count()
    return pct(done, total), f'{done} of {total} tasks are done.'


def _money(today, now):
    since = now - timedelta(days=CASH_TREND_DAYS)
    cash = LedgerLine.objects.filter(account__code='1000')
    recent = cash.filter(entry__posted_at__gte=since).aggregate(
        came_in=Sum('debit', default=0), went_out=Sum('credit', default=0),
    )
    came_in, went_out = recent['came_in'], recent['went_out']
    if came_in + went_out == 0:
        return None, f'No cash has moved in the last {CASH_TREND_DAYS} days.'
    totals = cash.aggregate(debit=Sum('debit', default=0), credit=Sum('credit', default=0))
    balance = totals['debit'] - totals['credit']
    # ASSUMPTION ("cash trend" is not defined in the plan): the share of
    # recent cash movement that was money coming in. 50 means in equals out.
    return pct(came_in, came_in + went_out), (
        f'In the last {CASH_TREND_DAYS} days {rupees(came_in)} came in and {rupees(went_out)} '
        f'went out; cash is now {rupees(balance)}.'
    )


def club_health(now=None):
    now = now or timezone.now()
    today = timezone.localdate(now)
    results = {
        'membership': _membership(today),
        'attendance': _attendance(today),
        'volunteering': _volunteering(today),
        'money': _money(today, now),
    }
    # ASSUMPTION: a component with nothing to measure is left out, and the
    # score is the weighted average of the rest, so a new club is not marked
    # down for having no closed events yet.
    counted = sum(WEIGHTS[key] for key, (score, _) in results.items() if score is not None)
    weighted = sum(WEIGHTS[key] * score for key, (score, _) in results.items() if score is not None)
    components = [
        {
            'key': key,
            'label': LABELS[key],
            'score': score,
            'weight': WEIGHTS[key],
            # Points this component adds to the overall score.
            'contribution': None if score is None else round(WEIGHTS[key] * score / counted, 1),
            'reason': reason,
        }
        for key, (score, reason) in results.items()
    ]
    return {
        'score': pct(weighted, counted * 100) if counted else None,
        'components': components,
    }
