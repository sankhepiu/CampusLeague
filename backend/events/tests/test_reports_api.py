from common.testing import ApiTestCase
from events.models import Ticket
from events.tests.helpers import make_event, make_member, make_tier
from events.tickets import scan
from finance.services import post_entry
from members.tests.test_services import make_plan
from shop.payments import purchase_membership, purchase_tickets


class EventReportTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.event = make_event(budget_amount=500000)
        self.general = make_tier(self.event, name='General', capacity=10)      # 80000 / 60000
        self.vip = make_tier(self.event, name='VIP', public_price=150000, member_price=120000, capacity=5)
        self.manager = self.make_role_user('event_manager')
        self.count = 0

    def buyer(self, member=False):
        self.count += 1
        user = self.make_user(email=f'b{self.count}@example.com', name=f'Buyer {self.count}', college_id=f'B{self.count}')
        if member:
            make_member(user)
        return user

    def sell(self, tier, quantity=1, member=False):
        return purchase_tickets(
            user=self.buyer(member), tier_id=tier.id, quantity=quantity,
            outcome='success', idempotency_key=f'report-key-{self.count:04}',
        ).tickets

    def get(self, name, event=None):
        return self.client.get(f'/api/events/{(event or self.event).id}/{name}')


class AttendanceTests(EventReportTestCase):
    def test_counts_sold_checked_in_and_no_shows_per_tier(self):
        general = self.sell(self.general, 3) + self.sell(self.general, 1)
        vip = self.sell(self.vip, 2)
        for ticket in general[:3] + vip[:1]:
            scan(operator=self.manager, token=ticket.qr_token)
        self.login_as(self.manager)

        body = self.get('attendance').json()

        self.assertEqual(body['event']['title'], 'Spring Gala')
        self.assertEqual(
            (body['capacity_total'], body['sold'], body['checked_in'], body['no_shows']), (100, 6, 4, 2),
        )
        self.assertEqual(body['attendance_rate_pct'], 66.7)
        self.assertEqual(
            [(t['name'], t['capacity'], t['sold'], t['checked_in'], t['no_shows']) for t in body['tiers']],
            [('General', 10, 4, 3, 1), ('VIP', 5, 2, 1, 1)],
        )

    def test_scanning_a_ticket_twice_counts_once(self):
        ticket = self.sell(self.general)[0]
        scan(operator=self.manager, token=ticket.qr_token)
        scan(operator=self.manager, token=ticket.qr_token)
        self.login_as(self.manager)
        self.assertEqual(self.get('attendance').json()['checked_in'], 1)

    def test_cancelled_tickets_are_not_counted_as_sold(self):
        tickets = self.sell(self.general, 2)
        Ticket.objects.filter(pk=tickets[0].pk).update(status='cancelled')
        self.login_as(self.manager)
        body = self.get('attendance').json()
        self.assertEqual((body['sold'], body['no_shows']), (1, 1))

    def test_event_with_no_sales(self):
        self.login_as(self.manager)
        body = self.get('attendance').json()
        self.assertEqual((body['sold'], body['checked_in'], body['no_shows']), (0, 0, 0))
        self.assertIsNone(body['attendance_rate_pct'])

    def test_other_events_are_not_mixed_in(self):
        other = make_event(title='Meetup')
        other_tier = make_tier(other)
        scan(operator=self.manager, token=self.sell(other_tier)[0].qr_token)
        self.sell(self.general)
        self.login_as(self.manager)
        body = self.get('attendance').json()
        self.assertEqual((body['sold'], body['checked_in']), (1, 0))


class PnlTests(EventReportTestCase):
    def expense(self, amount, source_id, event=None, account='5000'):
        # The posting Phase 4 will make when an expense is approved.
        post_entry(
            description='Catering', source_type='expense_request', source_id=source_id,
            kind='expense_approved', event=event or self.event,
            lines=[(account, amount, 0), ('2000', 0, amount)],
        )

    def test_revenue_comes_from_the_ledger_at_prices_actually_paid(self):
        self.sell(self.general, 2)                 # 2 x 80000 public
        self.sell(self.general, 1, member=True)    # 60000 member
        self.sell(self.vip, 1, member=True)        # 120000 member
        self.login_as(self.manager)

        body = self.get('pnl').json()

        self.assertEqual(body['revenue'], {
            'total': 340000,
            'by_account': [{'code': '4100', 'name': 'Ticket revenue', 'amount': 340000}],
        })
        self.assertEqual(body['expenses'], {'total': 0, 'by_account': []})
        self.assertEqual(body['profit'], 340000)
        # Reconciles with the source records.
        paid = sum(Ticket.objects.filter(event=self.event).values_list('price_paid', flat=True))
        self.assertEqual(body['revenue']['total'], paid)

    def test_expenses_reduce_profit_and_the_remaining_budget(self):
        self.sell(self.general, 5)                 # 400000
        self.expense(150000, source_id=1)
        self.expense(50000, source_id=2)
        self.login_as(self.manager)

        body = self.get('pnl').json()

        self.assertEqual(body['expenses'], {
            'total': 200000,
            'by_account': [{'code': '5000', 'name': 'Event expenses', 'amount': 200000}],
        })
        self.assertEqual(body['profit'], 200000)
        self.assertEqual(body['budget'], {'amount': 500000, 'spent': 200000, 'remaining': 300000})

    def test_a_loss_is_a_negative_profit_and_overspend_a_negative_remainder(self):
        self.sell(self.general, 1)                 # 80000
        self.expense(600000, source_id=1)
        self.login_as(self.manager)
        body = self.get('pnl').json()
        self.assertEqual(body['profit'], -520000)
        self.assertEqual(body['budget']['remaining'], -100000)

    def test_only_this_events_money_is_counted(self):
        other = make_event(title='Meetup')
        self.sell(make_tier(other), 2)
        self.expense(70000, source_id=1, event=other)
        purchase_membership(
            user=self.buyer(), plan=make_plan(name='Dues plan'), outcome='success',
            idempotency_key='report-dues-key',
        )
        self.sell(self.general, 1)
        self.login_as(self.manager)

        body = self.get('pnl').json()

        self.assertEqual((body['revenue']['total'], body['expenses']['total'], body['profit']), (80000, 0, 80000))

    def test_event_with_no_money_yet(self):
        self.login_as(self.manager)
        body = self.get('pnl').json()
        self.assertEqual((body['revenue']['total'], body['expenses']['total'], body['profit']), (0, 0, 0))
        self.assertEqual(body['budget'], {'amount': 500000, 'spent': 0, 'remaining': 500000})

    def test_includes_the_attendance_rate(self):
        tickets = self.sell(self.general, 4)
        scan(operator=self.manager, token=tickets[0].qr_token)
        self.login_as(self.manager)
        self.assertEqual(
            self.get('pnl').json()['attendance'], {'sold': 4, 'checked_in': 1, 'attendance_rate_pct': 25.0},
        )


class ReportPermissionTests(EventReportTestCase):
    def test_president_treasurer_and_event_manager_may_read(self):
        for role in ['president', 'treasurer']:
            self.login_as(self.make_role_user(role))
            for name in ['attendance', 'pnl']:
                with self.subTest(role=role, report=name):
                    self.assertEqual(self.get(name).status_code, 200)

    def test_everyone_else_is_refused(self):
        refused = [self.make_role_user('volunteer_coordinator'), self.make_role_user('member'), self.make_user()]
        for user in refused:
            self.login_as(user)
            for name in ['attendance', 'pnl']:
                with self.subTest(user=user.email, report=name):
                    self.assert_error(self.get(name), 403, 'permission_denied')
        self.client.credentials()
        for name in ['attendance', 'pnl']:
            self.assert_error(self.get(name), 401, 'not_authenticated')

    def test_ticket_holder_cannot_read_the_events_money(self):
        holder = self.buyer()
        purchase_tickets(user=holder, tier_id=self.general.id, quantity=1, outcome='success', idempotency_key='holder-key-9')
        self.login_as(holder)
        self.assert_error(self.get('pnl'), 403, 'permission_denied')

    def test_unknown_event_is_404(self):
        self.login_as(self.manager)
        for name in ['attendance', 'pnl']:
            self.assert_error(self.client.get(f'/api/events/999999/{name}'), 404, 'not_found')

    def test_reports_are_read_only(self):
        self.login_as(self.manager)
        self.assert_error(self.client.post(f'/api/events/{self.event.id}/pnl', {}, format='json'), 405, 'method_not_allowed')
