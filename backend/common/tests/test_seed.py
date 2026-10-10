from django.contrib.auth import authenticate, get_user_model
from django.core.management import CommandError, call_command
from django.db.models import F, Sum
from django.test import TransactionTestCase, override_settings

import os
import struct
import zlib
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from audit.models import AuditLog
from comms.models import Announcement
from common import seed
from events.models import CheckIn, Event, Ticket, TicketTier
from finance import reports
from finance.models import ExpenseRequest, LedgerAccount, LedgerEntry, LedgerLine
from finance.tests.helpers import TempMediaMixin
from insights import health, simulator
from insights.models import SaveFile
from finance.services import account_balance
from members.models import Membership
from members.services import membership_status
from shop import stock
from volunteering.models import Fundraiser
from volunteering.services import progress
from shop.models import Order, OrderLine, Payment, Product

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
        'products': Product.objects.count(), 'announcements': Announcement.objects.count(),
        'cash': account_balance('1000'),
    }


# Real commits (TransactionTestCase): the command's own transaction, the
# deferred ledger trigger and TRUNCATE all behave exactly as in development.
@override_settings(DEBUG=True)
class SeedDemoTests(TempMediaMixin, TransactionTestCase):
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
        self.assertEqual(account_balance('4000'), dues)
        self.assertEqual(account_balance('4100'), tickets)
        merch = sum(line.amount for line in OrderLine.objects.filter(kind='merch'))
        self.assertEqual(account_balance('4200'), merch)
        self.assertGreater(merch, 0)
        self.assertEqual(payments, dues + tickets + merch)

        totals = LedgerLine.objects.aggregate(debit=Sum('debit'), credit=Sum('credit'))
        self.assertEqual(totals['debit'], totals['credit'])
        # The app's own reconciliation endpoint agrees, check by check.
        result = reports.reconcile()
        self.assertEqual([check['name'] for check in result['checks'] if not check['ok']], [])
        self.assertTrue(result['ok'])
        self.assertGreater(account_balance('1000'), 0)
        self.assertEqual(Order.objects.exclude(status='paid').count(), 0)

    def test_every_ticket_revenue_entry_is_tagged_with_its_event(self):
        self.assertFalse(LedgerEntry.objects.filter(kind='ticket_sale', event__isnull=True).exists())
        self.assertFalse(LedgerEntry.objects.filter(kind='membership_dues', event__isnull=False).exists())

    def test_shop_has_two_products_with_one_size_nearly_sold_out(self):
        stock_levels = {
            product.name: {size.size: size.stock for size in product.sizes.all()}
            for product in Product.objects.all()
        }
        self.assertEqual(stock_levels, {
            'Skyline Hoodie': {'S': 8, 'M': 5, 'L': 6, 'XL': 1},
            'Skyline T-Shirt': {'S': 15, 'M': 16, 'L': 13, 'XL': 10},
        })
        self.assertEqual(stock.stock_mismatches(), [])
        # Every restock was audited.
        self.assertEqual(AuditLog.objects.filter(action='stock.restocked').count(), 8)

    def test_two_past_announcements_with_delivery_logs(self):
        announcements = list(Announcement.objects.all())
        self.assertEqual(len(announcements), 2)
        for announcement in announcements:
            self.assertLess(announcement.published_at, timezone.now() - timedelta(days=1))
            self.assertEqual(announcement.deliveries.count(), 46)
            self.assertFalse(announcement.deliveries.exclude(status='sent').exists())

    def test_fundraiser_tasks_and_expenses_match_the_demo_story(self):
        bake_sale = Fundraiser.objects.get(title='Bake Sale')
        figures = progress(bake_sale)
        self.assertEqual((figures['raised_amount'], figures['tasks_total'], figures['tasks_done']), (740000, 4, 1))
        self.assertTrue(0 < figures['raised_pct'] < 100)            # goal bar partly filled
        self.assertTrue(figures['on_track'])

        statuses = sorted(ExpenseRequest.objects.values_list('status', flat=True))
        self.assertEqual(statuses, ['approved', 'approved', 'paid', 'paid', 'paid', 'rejected', 'submitted', 'submitted'])
        for expense in ExpenseRequest.objects.all():
            self.assertTrue(os.path.exists(expense.receipt_file.path), expense)
            with open(expense.receipt_file.path, 'rb') as handle:
                self.assertEqual(handle.read(8), b'\x89PNG\r\n\x1a\n')
        # Nobody approved or paid their own request.
        for expense in ExpenseRequest.objects.exclude(status='submitted'):
            self.assertNotEqual(expense.approval.approver_id, expense.requester_id)

    def test_past_event_has_revenue_and_expenses(self):
        pnl = reports.event_pnl(Event.objects.get(title='Freshers Night'))
        self.assertEqual((pnl['revenue']['total'], pnl['expenses']['total'], pnl['profit']), (740000, 450000, 290000))

    def test_reset_removes_old_receipt_files(self):
        before = set(os.listdir(os.path.join(settings.MEDIA_ROOT, 'receipts')))
        run('--reset')
        after = set(os.listdir(os.path.join(settings.MEDIA_ROOT, 'receipts')))
        self.assertEqual(len(after), 8)
        self.assertEqual(before & after, set())

    def test_past_event_has_a_save_file(self):
        save_file = SaveFile.objects.get()
        self.assertEqual(save_file.event.title, 'Freshers Night')
        self.assertTrue(save_file.vendors and save_file.what_worked and save_file.what_didnt)
        self.assertEqual(len(save_file.checklist), 5)
        self.assertEqual(AuditLog.objects.filter(action='savefile.created').count(), 1)

    def test_simulator_shows_forecast_vs_actual_for_the_past_event(self):
        # Forecast made before Freshers Night: 40 guests at Rs 250, Rs 2,000
        # fixed costs, Rs 50 a head.
        freshers = Event.objects.get(title='Freshers Night')
        forecast = simulator.simulate(
            ticket_price=25000, expected_attendance=40, fixed_costs=200000, variable_cost_per_head=5000,
        )
        self.assertEqual(forecast['break_even_attendance'], 10)
        self.assertEqual((forecast['revenue'], forecast['costs'], forecast['profit']), (1000000, 400000, 600000))

        comparison = simulator.forecast_vs_actual(freshers, forecast, 40)

        # Actual, from the seed: 35 sold (31 members at Rs 200, 4 at Rs 300),
        # 30 checked in, expenses of Rs 2,500 + Rs 800 + Rs 1,200.
        self.assertEqual(comparison['actual'], {
            'attendance': 30, 'tickets_sold': 35, 'revenue': 740000, 'costs': 450000, 'profit': 290000,
        })
        self.assertEqual(comparison['forecast'], {'attendance': 40, 'revenue': 1000000, 'costs': 400000, 'profit': 600000})
        self.assertEqual(comparison['difference'], {'attendance': -10, 'revenue': -260000, 'costs': 50000, 'profit': -310000})
        # The upcoming gala has no "actual" yet.
        self.assertIsNone(simulator.forecast_vs_actual(Event.objects.get(title='Spring Gala'), forecast, 40))

    def test_club_health_explains_itself_on_the_demo_data(self):
        result = health.club_health()
        components = {component['key']: component for component in result['components']}
        # 41 of 45 active (40 members + 5 role accounts; 91%); 0 of 4 lapsed
        # renewed: (70*91 + 30*0) / 100 = 63.7 -> 64.
        self.assertEqual(components['membership']['score'], 64)
        self.assertIn('41 of 45', components['membership']['reason'])
        self.assertIn('0 of 4', components['membership']['reason'])
        # 30 of 35 checked in = 85.7 -> 86.
        self.assertEqual(components['attendance']['score'], 86)
        # 1 of 4 tasks done.
        self.assertEqual(components['volunteering']['score'], 25)
        # Cash in: dues 2,650,000 (40 members + 5 role accounts) + tickets
        # 2,820,000 + merch 1,328,000 (1,148,000 + 5 T-shirts at 36,000) +
        # bake sale 740,000 = 7,538,000 paise. Cash out: payouts of 250,000 +
        # 80,000 + 500,000 = 830,000. 7,538,000 / 8,368,000 = 90.1 -> 90.
        self.assertEqual(components['money']['score'], 90)
        self.assertIn('Rs 75,380.00 came in and Rs 8,300.00 went out', components['money']['reason'])
        # (64*30 + 86*25 + 25*20 + 90*25) / 100 = 68.2 -> 68.
        self.assertEqual(result['score'], 68)
        self.assertEqual(
            round(sum(component['contribution'] for component in result['components'])), result['score'],
        )

    def test_every_role_account_has_data_on_every_screen(self):
        gala = Event.objects.get(title='Spring Gala')
        for prefix in ['president', 'treasurer', 'events', 'volunteers', 'approver']:
            with self.subTest(account=prefix):
                user = User.objects.get(email=f'{prefix}@skyline.test')
                self.assertEqual(membership_status(user), 'active')
                self.assertEqual(Ticket.objects.filter(owner=user, event=gala, status='valid').count(), 1)
                self.assertEqual(Order.objects.filter(buyer=user, lines__kind='merch', status='paid').count(), 1)
                self.assertTrue(user.current_roles())

        treasurer = User.objects.get(email='treasurer@skyline.test')
        own = ExpenseRequest.objects.filter(requester=treasurer)
        self.assertEqual([expense.status for expense in own], ['submitted'])       # exactly one, pending

        coordinator = User.objects.get(email='volunteers@skyline.test')
        self.assertGreaterEqual(
            coordinator.task_assignments.filter(task__fundraiser__title='Bake Sale').count(), 1,
        )

    def test_products_have_generated_pixel_art_images(self):
        images = {product.name: product.image.name for product in Product.objects.all()}
        self.assertEqual(images, {
            'Skyline Hoodie': 'products/skyline-hoodie.png', 'Skyline T-Shirt': 'products/skyline-t-shirt.png',
        })
        contents = []
        for product in Product.objects.all():
            with open(product.image.path, 'rb') as handle:
                data = handle.read()
            self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n')
            self.assertEqual(struct.unpack('>II', data[16:24]), (256, 256))
            # Every chunk's CRC is right, so image viewers will accept it.
            position = 8
            while position < len(data):
                length = struct.unpack('>I', data[position:position + 4])[0]
                body = data[position + 4:position + 8 + length]
                self.assertEqual(struct.unpack('>I', data[position + 8 + length:position + 12 + length])[0], zlib.crc32(body))
                position += 12 + length
            contents.append(data)
        self.assertNotEqual(contents[0], contents[1])           # two distinct pictures

    def test_reseeding_keeps_the_same_image_file_names(self):
        run('--reset')
        self.assertEqual(sorted(os.listdir(os.path.join(settings.MEDIA_ROOT, 'products'))),
                         ['skyline-hoodie.png', 'skyline-t-shirt.png'])

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
        # The marker written before the reset is gone; the only audit rows
        # are the ones the seed itself writes.
        self.assertFalse(AuditLog.objects.filter(action='test.marker').exists())
        self.assertEqual(AuditLog.objects.filter(action='stock.restocked').count(), 8)
        # ...plus 5 approvals, 3 payouts, 1 rejection and 1 save file.
        self.assertEqual(AuditLog.objects.count(), 8 + 9 + 1)
        self.assertEqual(LedgerAccount.objects.count(), 9)     # chart of accounts kept
        self.assertEqual(Event.objects.order_by('id').first().id, 1)   # ids restart

    @override_settings(DEBUG=False)
    def test_refuses_to_run_outside_debug(self):
        before = snapshot()
        with self.assertRaises(CommandError):
            run('--reset')
        self.assertEqual(snapshot(), before)
