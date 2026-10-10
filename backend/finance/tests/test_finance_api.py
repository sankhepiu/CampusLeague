from common.testing import ApiTestCase
from events.tests.helpers import make_event, make_member, make_tier
from events.tickets import scan
from finance import expenses, reports
from finance.models import ExpenseRequest
from members.tests.test_services import make_plan
from shop.models import OrderLine, ProductSize
from shop.payments import purchase_membership, purchase_merch, purchase_tickets
from shop.tests.helpers import make_product, size_of
from volunteering.models import Fundraiser
from volunteering.services import record_sale


class FinanceTestCase(ApiTestCase):
    """A small club with one of everything, built through the real flows."""

    def setUp(self):
        super().setUp()
        self.treasurer = self.make_role_user('treasurer')
        self.president = self.make_role_user('president')
        self.manager = self.make_role_user('event_manager')
        self.priya = self.make_user()
        self.event = make_event(budget_amount=500000)
        self.tier = make_tier(self.event)                     # 80000 public / 60000 member
        self.hoodie = make_product('Hoodie', 120000, {'M': 5})

        purchase_membership(user=self.priya, plan=make_plan(price=50000, merch_discount_pct=10),
                            outcome='success', idempotency_key='fin-dues-0001')                      # +50000 dues
        self.tickets = purchase_tickets(user=self.priya, tier_id=self.tier.id, quantity=2,
                                        outcome='success', idempotency_key='fin-tix-00001').tickets   # +120000 tickets
        scan(operator=self.manager, token=self.tickets[0].qr_token)
        purchase_merch(user=self.priya, items={size_of(self.hoodie, 'M').pk: 1},
                       outcome='success', idempotency_key='fin-merch-0001')                           # +108000 merch
        self.fundraiser = Fundraiser.objects.create(title='Bake Sale', goal_amount=100000, starts_on='2026-10-01', ends_on='2026-10-31')
        record_sale(fundraiser=self.fundraiser, amount=30000, recorded_by=self.president, note='Saturday stall')  # +30000

        self.paid = self.expense(70000, 'Catering')           # approved and paid:  cash -70000
        expenses.approve(self.paid.pk, self.treasurer)
        expenses.mark_paid(self.paid.pk, self.president)
        self.owed = self.expense(20000, 'Decorations')        # approved, unpaid:   payable 20000
        expenses.approve(self.owed.pk, self.treasurer)
        self.expense(999999, 'Not yet decided')               # submitted: no effect
        self.login_as(self.treasurer)

    def expense(self, amount, description):
        return ExpenseRequest.objects.create(
            requester=self.priya, amount=amount, category='event', event=self.event,
            description=description, receipt_file='receipts/test.png',
        )


class SummaryTests(FinanceTestCase):
    def test_came_in_went_out_and_whats_left(self):
        body = self.client.get('/api/finance/summary').json()

        self.assertEqual(body['came_in'], {'total': 308000, 'by_account': [
            {'code': '4000', 'name': 'Membership dues revenue', 'amount': 50000},
            {'code': '4100', 'name': 'Ticket revenue', 'amount': 120000},
            {'code': '4200', 'name': 'Merchandise revenue', 'amount': 108000},
            {'code': '4300', 'name': 'Fundraiser revenue', 'amount': 30000},
        ]})
        self.assertEqual(body['went_out'], {'total': 90000, 'by_account': [
            {'code': '5000', 'name': 'Event expenses', 'amount': 90000},
        ]})
        self.assertEqual(body['net'], 218000)
        self.assertEqual(body['cash'], 238000)          # 308000 in, 70000 actually paid out
        self.assertEqual(body['payable'], 20000)        # approved, not yet paid

    def test_empty_ledger_is_all_zeros(self):
        from finance.models import LedgerLine
        self.assertTrue(LedgerLine.objects.exists())
        # A fresh club: computed on a filter that matches nothing.
        empty = reports._account_totals(LedgerLine.objects.none())
        self.assertEqual(empty, {'asset': [], 'liability': [], 'revenue': [], 'expense': []})


class ReconcileTests(FinanceTestCase):
    def test_everything_reconciles_after_a_full_set_of_flows(self):
        body = self.client.get('/api/finance/reconcile').json()
        failing = [check for check in body['checks'] if not check['ok']]
        self.assertEqual(failing, [])
        self.assertTrue(body['ok'])
        self.assertEqual(len(body['checks']), 11)

    def test_detects_a_source_record_changed_behind_the_ledgers_back(self):
        # Someone edits an order line's price directly in the database.
        OrderLine.objects.filter(kind='ticket').update(unit_price=1)
        body = self.client.get('/api/finance/reconcile').json()
        self.assertFalse(body['ok'])
        failing = {check['name']: check for check in body['checks'] if not check['ok']}
        self.assertEqual(list(failing), ['Ticket revenue equals paid ticket order lines'])
        check = failing['Ticket revenue equals paid ticket order lines']
        self.assertEqual((check['expected'], check['actual']), (2, 120000))

    def test_detects_stock_edited_without_a_movement(self):
        ProductSize.objects.filter(product=self.hoodie, size='M').update(stock=99)
        body = self.client.get('/api/finance/reconcile').json()
        self.assertFalse(body['ok'])
        self.assertEqual([c['name'] for c in body['checks'] if not c['ok']],
                         ['Stock on hand equals the sum of stock movements (sizes that differ)'])

    def test_detects_an_expense_marked_paid_without_a_ledger_entry(self):
        ExpenseRequest.objects.filter(pk=self.owed.pk).update(status='paid')
        body = self.client.get('/api/finance/reconcile').json()
        self.assertFalse(body['ok'])
        self.assertGreaterEqual(len([c for c in body['checks'] if not c['ok']]), 1)


class LedgerListTests(FinanceTestCase):
    def test_lists_entries_newest_first_with_their_lines(self):
        body = self.client.get('/api/finance/ledger').json()
        self.assertEqual(body['count'], 7)        # dues, tickets, merch, fundraiser, approve, pay, approve
        first = body['results'][0]
        self.assertEqual(set(first), {'id', 'posted_at', 'description', 'source_type', 'source_id', 'kind', 'event', 'reverses', 'lines'})
        for entry in body['results']:
            self.assertEqual(sum(l['debit'] for l in entry['lines']), sum(l['credit'] for l in entry['lines']))

    def test_filters(self):
        get = lambda **params: self.client.get('/api/finance/ledger', params).json()['count']
        self.assertEqual(get(account='4100'), 1)
        self.assertEqual(get(account='1000'), 5)             # every entry that touched cash
        self.assertEqual(get(event=self.event.id), 4)        # tickets + 3 expense entries
        self.assertEqual(get(kind='expense_approved'), 2)
        self.assertEqual(get(account='9999'), 0)
        self.assert_error(self.client.get('/api/finance/ledger', {'event': 'gala'}), 400, 'validation_error', field='event')

    def test_ledger_is_read_only(self):
        self.assert_error(self.client.post('/api/finance/ledger', {}, format='json'), 405, 'method_not_allowed')


class TraceTests(FinanceTestCase):
    def trace(self, figure):
        response = self.client.get('/api/finance/trace', {'figure': figure})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_every_summary_figure_traces_to_the_same_total(self):
        summary = self.client.get('/api/finance/summary').json()
        self.assertEqual(self.trace('came_in')['total'], summary['came_in']['total'])
        self.assertEqual(self.trace('went_out')['total'], summary['went_out']['total'])
        self.assertEqual(self.trace('cash')['total'], summary['cash'])
        self.assertEqual(self.trace('payable')['total'], summary['payable'])
        for account in summary['came_in']['by_account']:
            self.assertEqual(self.trace(f"account:{account['code']}")['total'], account['amount'])

    def test_event_profit_unfolds_to_tickets_checkin_and_receipts(self):
        body = self.trace(f'event:{self.event.id}:profit')

        self.assertEqual(body['total'], 120000 - 90000)
        self.assertEqual(sum(entry['amount'] for entry in body['entries']), body['total'])
        by_type = {}
        for entry in body['entries']:
            by_type.setdefault(entry['source']['type'], []).append(entry)

        ticket_entry = by_type['order_line'][0]
        self.assertEqual(ticket_entry['amount'], 120000)
        tickets = ticket_entry['source']['details']['tickets']
        self.assertEqual([t['holder'] for t in tickets], ['Priya', 'Priya'])
        self.assertEqual(sorted(t['code'] for t in tickets), sorted(t.code for t in self.tickets))
        self.assertEqual(sum(1 for t in tickets if t['checked_in_at']), 1)       # down to a specific check-in

        expense_entries = by_type['expense_request']
        self.assertEqual(sorted(e['amount'] for e in expense_entries), [-70000, -20000])
        self.assertIn('receipts/', expense_entries[0]['source']['details']['receipt_url'])
        self.assertEqual(expense_entries[0]['source']['details']['approved_by'], self.treasurer.name)

    def test_event_revenue_and_expenses_separately(self):
        self.assertEqual(self.trace(f'event:{self.event.id}:revenue')['total'], 120000)
        self.assertEqual(self.trace(f'event:{self.event.id}:expenses')['total'], 90000)

    def test_event_trace_agrees_with_the_pnl_endpoint(self):
        pnl = self.client.get(f'/api/events/{self.event.id}/pnl').json()
        self.assertEqual(self.trace(f'event:{self.event.id}:profit')['total'], pnl['profit'])

    def test_sources_for_dues_merch_and_fundraiser(self):
        dues = self.trace('account:4000')['entries'][0]['source']
        self.assertEqual((dues['type'], dues['details']['member']), ('payment', 'Priya'))
        merch = self.trace('account:4200')['entries'][0]['source']
        self.assertEqual(merch['details']['items'], [
            {'product': 'Hoodie', 'size': 'M', 'qty': 1, 'unit_price': 120000, 'discount': 12000, 'paid': 108000},
        ])
        sale = self.trace('account:4300')['entries'][0]['source']
        self.assertEqual((sale['type'], sale['details']['amount']), ('fundraiser_sale', 30000))

    def test_unknown_figures_are_a_400(self):
        for figure in ['', 'profit', 'account:9999', 'event:999999:profit', 'event:x:profit', f'event:{self.event.id}:vibes', "account:1000'; DROP TABLE"]:
            with self.subTest(figure=figure):
                response = self.client.get('/api/finance/trace', {'figure': figure})
                self.assert_error(response, 400, 'validation_error', field='figure')


class FinancePermissionTests(FinanceTestCase):
    URLS = ['/api/finance/summary', '/api/finance/ledger', '/api/finance/reconcile', '/api/finance/trace?figure=cash']

    def test_president_and_treasurer_may_read(self):
        for user in [self.treasurer, self.president]:
            self.login_as(user)
            for url in self.URLS:
                with self.subTest(user=user.email, url=url):
                    self.assertEqual(self.client.get(url).status_code, 200)

    def test_everyone_else_is_refused(self):
        refused = [self.manager, self.make_role_user('volunteer_coordinator'), self.make_role_user('member'), self.priya]
        for user in refused:
            self.login_as(user)
            for url in self.URLS:
                with self.subTest(user=user.email, url=url):
                    self.assert_error(self.client.get(url), 403, 'permission_denied')
        self.client.credentials()
        for url in self.URLS:
            self.assert_error(self.client.get(url), 401, 'not_authenticated')
