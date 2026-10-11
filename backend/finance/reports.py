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


# Treasurer view ----------------------------------------------------------

def _account_totals(lines):
    """Per-account net amounts for a set of ledger lines, split by type."""
    rows = (
        lines.values('account__code', 'account__name', 'account__type')
        .annotate(debit=Sum('debit'), credit=Sum('credit')).order_by('account__code')
    )
    result = {'asset': [], 'liability': [], 'revenue': [], 'expense': []}
    for row in rows:
        debit_normal = row['account__type'] in ('asset', 'expense')
        amount = row['debit'] - row['credit'] if debit_normal else row['credit'] - row['debit']
        result[row['account__type']].append(
            {'code': row['account__code'], 'name': row['account__name'], 'amount': amount}
        )
    return result


def _total(items):
    return sum(item['amount'] for item in items)


def summary():
    """Plan: "What came in, went out, and what's left? Sum revenue, sum
    expenses, and the cash account balance." (R17)
    """
    totals = _account_totals(LedgerLine.objects.all())
    came_in, went_out = _total(totals['revenue']), _total(totals['expense'])
    return {
        'came_in': {'total': came_in, 'by_account': totals['revenue']},
        'went_out': {'total': went_out, 'by_account': totals['expense']},
        'net': came_in - went_out,
        # What is actually in the bank now.
        'cash': _total(totals['asset']),
        # Approved reimbursements not yet paid out.
        'payable': _total(totals['liability']),
    }


def reconcile():
    """Plan: "Reconciliation check: cash balance equals revenue minus
    expenses plus payables movement, and each revenue total equals the sum
    of its source records."

    Each check compares a figure derived from the ledger with the same
    figure derived independently from the source tables.
    """
    from django.db.models import F

    from events.models import TicketTier
    from shop.models import OrderLine, Payment
    from shop.stock import stock_mismatches
    from volunteering.models import FundraiserSale

    from .models import ExpenseRequest
    from .services import account_balance

    def paid_lines(kind):
        lines = OrderLine.objects.filter(kind=kind, order__status='paid')
        return lines.aggregate(total=Sum(F('qty') * F('unit_price') - F('discount'), default=0))['total']

    def expenses(*statuses):
        return ExpenseRequest.objects.filter(status__in=statuses).aggregate(total=Sum('amount', default=0))['total']

    totals = LedgerLine.objects.aggregate(debit=Sum('debit', default=0), credit=Sum('credit', default=0))
    figures = summary()
    payments = Payment.objects.aggregate(total=Sum('amount', default=0))['total']
    fundraising = FundraiserSale.objects.aggregate(total=Sum('amount', default=0))['total']
    tickets_sold = Ticket.objects.exclude(status=Ticket.Status.CANCELLED).count()
    seats_counted = TicketTier.objects.aggregate(total=Sum('sold_count', default=0))['total']

    checks = [
        ('Ledger balances: total debits equal total credits', totals['credit'], totals['debit']),
        ('Cash equals revenue minus expenses plus unpaid reimbursements',
         figures['came_in']['total'] - figures['went_out']['total'] + figures['payable'], figures['cash']),
        ('Cash equals payments received plus fundraiser takings minus reimbursements paid',
         payments + fundraising - expenses('paid'), figures['cash']),
        ('Membership dues revenue equals paid membership order lines', paid_lines('membership'), account_balance('4000')),
        ('Ticket revenue equals paid ticket order lines', paid_lines('ticket'), account_balance('4100')),
        ('Merchandise revenue equals paid merch order lines', paid_lines('merch'), account_balance('4200')),
        ('Fundraiser revenue equals recorded fundraiser sales', fundraising, account_balance('4300')),
        ('Expenses equal approved and paid expense requests', expenses('approved', 'paid'), figures['went_out']['total']),
        ('Reimbursements payable equals approved, unpaid expense requests', expenses('approved'), figures['payable']),
        ('Seats sold on tiers equal tickets issued', tickets_sold, seats_counted),
        ('Stock on hand equals the sum of stock movements (sizes that differ)', 0, len(stock_mismatches())),
    ]
    results = [
        {'name': name, 'ok': expected == actual, 'expected': expected, 'actual': actual}
        for name, expected, actual in checks
    ]
    return {'ok': all(check['ok'] for check in results), 'checks': results}


# Coin Trail --------------------------------------------------------------

def _local(moment):
    """A timestamp in the site's time zone, as the rest of the API sends them."""
    from django.utils import timezone

    return timezone.localtime(moment) if moment else None


def _coupon_code(order):
    return order.coupon.code if order.coupon_id else None


def _source(entry):
    """The record behind a ledger entry, as {type, id, label, details}."""
    from shop.models import Order, OrderLine, Payment
    from volunteering.models import FundraiserSale

    from .models import ExpenseRequest

    kind, source_id = entry.source_type, entry.source_id
    base = {'type': kind, 'id': source_id}
    if kind == 'payment':
        payment = Payment.objects.select_related('order__buyer').get(pk=source_id)
        line = payment.order.lines.select_related('plan', 'membership').first()
        return {**base, 'label': f'{payment.order.buyer.name} paid dues for {line.plan.name}', 'details': {
            'order': payment.order_id, 'member': payment.order.buyer.name, 'plan': line.plan.name,
            'membership': line.membership_id, 'amount': payment.amount,
            'list_price': line.qty * line.unit_price, 'discount': line.discount,
            'coupon': _coupon_code(payment.order), 'coupon_discount': line.coupon_discount,
        }}
    if kind == 'order_line':
        line = OrderLine.objects.select_related('order__buyer', 'tier__event').get(pk=source_id)
        tickets = [
            {
                'type': 'ticket', 'id': ticket.id, 'code': ticket.code, 'holder': ticket.owner.name,
                'price_paid': ticket.price_paid, 'status': ticket.status,
                'checked_in_at': _local(getattr(getattr(ticket, 'checkin', None), 'scanned_at', None)),
            }
            for ticket in Ticket.objects.filter(order=line.order, tier=line.tier).select_related('owner', 'checkin')
        ]
        return {**base, 'label': f'{line.order.buyer.name} bought {line.qty} x {line.tier.name} for {line.tier.event.title}',
                'details': {
                    'order': line.order_id, 'buyer': line.order.buyer.name, 'tickets': tickets,
                    'list_price': line.qty * line.unit_price, 'discount': line.discount, 'paid': line.amount,
                    'coupon': _coupon_code(line.order), 'coupon_discount': line.coupon_discount,
                }}
    if kind == 'order':
        order = Order.objects.select_related('buyer').get(pk=source_id)
        items = [
            {'product': line.product_size.product.name, 'size': line.product_size.size, 'qty': line.qty,
             'unit_price': line.unit_price, 'discount': line.discount,
             'coupon_discount': line.coupon_discount, 'paid': line.amount}
            for line in order.lines.filter(kind='merch').select_related('product_size__product')
        ]
        return {**base, 'label': f'{order.buyer.name} ordered merchandise', 'details': {
            'order': order.pk, 'buyer': order.buyer.name, 'items': items,
            'discount': order.discount, 'coupon': _coupon_code(order), 'coupon_discount': order.coupon_discount,
        }}
    if kind == 'expense_request':
        expense = ExpenseRequest.objects.select_related('requester').get(pk=source_id)
        approval = getattr(expense, 'approval', None)
        return {**base, 'label': f'{expense.requester.name}: {expense.description}', 'details': {
            'requester': expense.requester.name, 'amount': expense.amount, 'status': expense.status,
            'receipt_url': expense.receipt_file.url,
            'description': expense.description,
            # Only an approval names an approver; a rejection does not.
            'approved_by': approval.approver.name if approval and approval.decision == 'approved' else None,
        }}
    if kind == 'fundraiser_sale':
        sale = FundraiserSale.objects.select_related('fundraiser', 'recorded_by').get(pk=source_id)
        return {**base, 'label': f'{sale.fundraiser.title}: {sale.note or "sale"}', 'details': {
            'fundraiser': sale.fundraiser_id, 'amount': sale.amount, 'recorded_by': sale.recorded_by.name,
        }}
    return {**base, 'label': entry.description, 'details': {}}


# figure name -> (label, account type or None, account code or None)
TRACE_FIGURES = {
    'came_in': ('Came in', 'revenue', None),
    'went_out': ('Went out', 'expense', None),
    'cash': ('Cash and bank', None, '1000'),
    'payable': ('Reimbursements payable', None, '2000'),
}


class UnknownFigure(ValueError):
    pass


def trace(figure, limit=200):
    """Plan: "Trace endpoint: total, then entries, then lines, then source
    records" (the Coin Trail).

    figure is one of: came_in, went_out, cash, payable, account:<code>,
    event:<id>:revenue, event:<id>:expenses, event:<id>:profit.
    """
    from events.models import Event

    lines = LedgerLine.objects.all()
    parts = figure.split(':')
    sign_by_type = {'asset': 1, 'expense': 1, 'revenue': -1, 'liability': -1}   # multiplies (debit - credit)

    if figure in TRACE_FIGURES:
        label, account_type, code = TRACE_FIGURES[figure]
        lines = lines.filter(account__type=account_type) if account_type else lines.filter(account__code=code)
        profit = False
    elif parts[0] == 'account' and len(parts) == 2:
        account = LedgerAccount.objects.filter(code=parts[1]).first()
        if account is None:
            raise UnknownFigure(figure)
        label, lines, profit = account.name, lines.filter(account=account), False
    elif parts[0] == 'event' and len(parts) == 3 and parts[1].isdigit() and parts[2] in ('revenue', 'expenses', 'profit'):
        event = Event.objects.filter(pk=int(parts[1])).first()
        if event is None:
            raise UnknownFigure(figure)
        lines = lines.filter(entry__event=event)
        wanted = {'revenue': [REVENUE], 'expenses': [EXPENSE], 'profit': [REVENUE, EXPENSE]}[parts[2]]
        lines = lines.filter(account__type__in=wanted)
        label, profit = f'{event.title}: {parts[2]}', parts[2] == 'profit'
    else:
        raise UnknownFigure(figure)

    def contribution(line):
        """How much this line adds to the figure."""
        amount = (line.debit - line.credit) * sign_by_type[line.account.type]
        # In a profit figure, expenses count against it.
        return -amount if profit and line.account.type == EXPENSE else amount

    # Step 1: the amounts. Only the lines on the figure's accounts count
    # towards each entry's amount and the total.
    counted_lines = list(lines.select_related('account', 'entry').order_by('-entry__posted_at', '-entry_id', 'id'))
    entries = {}
    for line in counted_lines:
        node = entries.setdefault(line.entry_id, {'entry': line.entry, 'amount': 0, 'lines': []})
        node['amount'] += contribution(line)
    nodes = list(entries.values())

    # Step 2: the display. Every line of each returned entry is shown, so the
    # reader sees both sides of it (a sale's revenue credit AND its cash
    # debit); "counted" marks the lines that made up the amount in step 1.
    counted_ids = {line.id for line in counted_lines}
    shown = {node['entry'].id: node for node in nodes[:limit]}
    for line in LedgerLine.objects.filter(entry_id__in=shown).select_related('account').order_by('id'):
        shown[line.entry_id]['lines'].append({
            'id': line.id, 'account': {'code': line.account.code, 'name': line.account.name},
            'debit': line.debit, 'credit': line.credit, 'counted': line.id in counted_ids,
        })
    return {
        'figure': figure,
        'label': label,
        'total': sum(node['amount'] for node in nodes),
        'entry_count': len(nodes),
        # Newest first; capped so one request cannot return the whole ledger.
        'entries': [
            {
                'id': node['entry'].id, 'posted_at': node['entry'].posted_at,
                'description': node['entry'].description, 'kind': node['entry'].kind,
                'amount': node['amount'], 'lines': node['lines'], 'source': _source(node['entry']),
            }
            for node in nodes[:limit]
        ],
    }
