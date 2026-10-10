from django.contrib.auth import authenticate, get_user_model
from django.core.management import CommandError, call_command
from django.db.models import F, Sum
from django.test import TransactionTestCase, override_settings

from audit.models import AuditLog
from common import seed
from events.models import CheckIn, Event, Ticket, TicketTier
from finance.models import LedgerAccount, LedgerEntry, LedgerLine
from finance.services import account_balance
from members.models import Membership
from members.services import membership_status
from shop.models import Order, OrderLine, Payment

User = get_user_model()


def run(*args):
    with open('/dev/null', 'w') as devnull:
        call_command('seed_demo', *args, stdout=devnull)


def snapshot():
    return {
        'users': User.objects.count(), 'memberships': Membership.objects.count(),
        'events': Event.objects.count(), 'tickets': Ticket.objects.count(),
        'checkins': CheckIn.objects.count(), 'orders': Order.objects.count(),
        'payments': Payment.objects.count(), 'entries': LedgerEntry.objects.count(),
        'cash': account_balance('1000'),
    }


# Real commits (TransactionTestCase): the command's own transaction, the
# deferred ledger trigger and TRUNCATE all behave exactly as in development.
@override_settings(DEBUG=True)
class SeedDemoTests(TransactionTestCase):
    serialized_rollback = True

    def setUp(self):
        run()

    def test_club_people_and_roles(self):
        self.assertEqual(User.objects.count(), 46)        # admin + 5 leaders + 40 members
        roles = {user.email.split('@')[0]: user.current_roles() for user in User.objects.all() if user.current_roles()}
        self.assertEqual(roles, {
            'president': ['president'], 'treasurer': ['treasurer'], 'events': ['event_manager'],
            'volunteers': ['volunteer_coordinator'], 'approver': ['treasurer'],
        })

    def test_priya_has_not_joined(self):
        self.assertFalse(User.objects.filter(email__icontains='priya').exists())
        self.assertFalse(User.objects.filter(name__icontains='priya').exists())

    def test_demo_logins_work(self):
        for email in ['president@skyline.test', 'member01@skyline.test', 'approver@skyline.test']:
            self.assertIsNotNone(authenticate(email=email, password=seed.DEMO_PASSWORD), email)
        self.assertIsNone(authenticate(email='president@skyline.test', password='wrong'))

    def test_members_are_a_mix_of_active_lapsed_and_expiring(self):
        members = User.objects.filter(email__startswith='member')
        statuses = [membership_status(member) for member in members]
        self.assertEqual((statuses.count('active'), statuses.count('lapsed'), statuses.count('none')), (36, 4, 0))
        self.assertEqual(sorted(Membership.objects.values_list('plan__name', flat=True).distinct()), ['Basic', 'Plus'])

    def test_events_match_the_demo_story(self):
        gala = Event.objects.get(title='Spring Gala')
        general = TicketTier.objects.get(event=gala, name='General')
        self.assertEqual(gala.status, 'on_sale')
        self.assertEqual(general.seats_left, 12)          # the demo's "12 seats left"
        self.assertEqual(gala.tiers.count(), 2)

        past = Event.objects.get(title='Freshers Night')
        self.assertEqual(past.status, 'closed')
        self.assertEqual(Ticket.objects.filter(event=past).count(), 35)
        self.assertEqual(CheckIn.objects.filter(ticket__event=past).count(), 30)

    def test_sold_counts_match_the_tickets_that_exist(self):
        for tier in TicketTier.objects.all():
            self.assertEqual(tier.sold_count, Ticket.objects.filter(tier=tier).count(), tier)

    def test_ledger_reconciles_with_the_source_records(self):
        # Plan: "Reconciliation check passes after the seed script."
        payments = Payment.objects.aggregate(total=Sum('amount'))['total']
        dues = OrderLine.objects.filter(kind='membership').aggregate(total=Sum(F('qty') * F('unit_price')))['total']
        tickets = Ticket.objects.aggregate(total=Sum('price_paid'))['total']
        self.assertEqual(account_balance('1000'), payments)
        self.assertEqual(account_balance('4000'), dues)
        self.assertEqual(account_balance('4100'), tickets)
        self.assertEqual(payments, dues + tickets)

        totals = LedgerLine.objects.aggregate(debit=Sum('debit'), credit=Sum('credit'))
        self.assertEqual(totals['debit'], totals['credit'])
        # One entry per source: a payment per membership, a line per ticket order.
        self.assertEqual(LedgerEntry.objects.count(), Payment.objects.count())
        self.assertEqual(Order.objects.exclude(status='paid').count(), 0)

    def test_every_ticket_revenue_entry_is_tagged_with_its_event(self):
        self.assertFalse(LedgerEntry.objects.filter(kind='ticket_sale', event__isnull=True).exists())
        self.assertFalse(LedgerEntry.objects.filter(kind='membership_dues', event__isnull=False).exists())

    def test_refuses_to_seed_twice_without_reset(self):
        before = snapshot()
        with self.assertRaises(CommandError):
            run()
        self.assertEqual(snapshot(), before)

    def test_reset_rebuilds_the_same_state_despite_the_append_only_triggers(self):
        before = snapshot()
        AuditLog.objects.create(action='test.marker', object_type='x', object_id=1)

        run('--reset')
        run('--reset')

        self.assertEqual(snapshot(), before)
        self.assertEqual(AuditLog.objects.count(), 0)
        self.assertEqual(LedgerAccount.objects.count(), 9)     # chart of accounts kept
        self.assertEqual(Event.objects.order_by('id').first().id, 1)   # ids restart

    @override_settings(DEBUG=False)
    def test_refuses_to_run_outside_debug(self):
        before = snapshot()
        with self.assertRaises(CommandError):
            run('--reset')
        self.assertEqual(snapshot(), before)
