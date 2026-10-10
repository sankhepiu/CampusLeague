from datetime import timedelta

from django.test import SimpleTestCase
from django.utils import timezone

from common.testing import ApiTestCase
from events.models import Event
from events.tests.helpers import make_event, make_tier
from events.tickets import scan
from finance.models import LedgerEntry
from finance.services import post_entry
from insights.simulator import NoBreakEven, simulate
from shop.payments import purchase_tickets

SIMULATOR = '/api/simulator'


def run(price, attendance, fixed, variable):
    return simulate(ticket_price=price, expected_attendance=attendance, fixed_costs=fixed, variable_cost_per_head=variable)


class BreakEvenMathsTests(SimpleTestCase):
    """No database: the calculation on its own."""

    def test_worked_example(self):
        # Rs 500 ticket, Rs 100 a head, Rs 10,000 fixed: margin Rs 400, 25 guests to break even.
        result = run(50000, 60, 1000000, 10000)
        self.assertEqual(result, {
            'margin_per_head': 40000, 'break_even_attendance': 25,
            'revenue': 3000000, 'costs': 1600000, 'profit': 1400000, 'breaks_even': True,
        })

    def test_break_even_is_rounded_up_to_a_whole_person(self):
        self.assertEqual(run(50000, 0, 1000001, 10000)['break_even_attendance'], 26)    # 25.000025
        self.assertEqual(run(50000, 0, 1000000, 10000)['break_even_attendance'], 25)    # exactly 25
        self.assertEqual(run(50000, 0, 999999, 10000)['break_even_attendance'], 25)     # 24.999975
        self.assertEqual(run(50000, 0, 1, 10000)['break_even_attendance'], 1)           # one paisa of cost

    def test_profit_is_zero_or_more_exactly_from_the_break_even_point(self):
        for fixed in [1, 39999, 40000, 40001, 1000000, 1234567]:
            with self.subTest(fixed=fixed):
                point = run(50000, 0, fixed, 10000)['break_even_attendance']
                self.assertGreaterEqual(run(50000, point, fixed, 10000)['profit'], 0)
                self.assertLess(run(50000, point - 1, fixed, 10000)['profit'], 0)

    def test_attendance_exactly_at_break_even(self):
        result = run(50000, 25, 1000000, 10000)
        self.assertEqual((result['profit'], result['breaks_even']), (0, True))
        below = run(50000, 24, 1000000, 10000)
        self.assertEqual((below['profit'], below['breaks_even']), (-40000, False))

    def test_no_fixed_costs_breaks_even_with_nobody(self):
        result = run(50000, 10, 0, 10000)
        self.assertEqual((result['break_even_attendance'], result['profit'], result['breaks_even']), (0, 400000, True))

    def test_zero_attendance_loses_the_fixed_costs(self):
        result = run(50000, 0, 1000000, 10000)
        self.assertEqual((result['revenue'], result['costs'], result['profit']), (0, 1000000, -1000000))

    def test_no_variable_cost(self):
        self.assertEqual(run(50000, 10, 100000, 0)['break_even_attendance'], 2)

    def test_zero_margin_is_refused_not_a_division_by_zero(self):
        with self.assertRaises(NoBreakEven):
            run(10000, 100, 500000, 10000)

    def test_negative_margin_is_refused(self):
        with self.assertRaises(NoBreakEven):
            run(10000, 100, 500000, 10001)

    def test_free_event_is_refused(self):
        with self.assertRaises(NoBreakEven):
            run(0, 100, 500000, 0)

    def test_smallest_positive_margin_works(self):
        self.assertEqual(run(10001, 0, 500000, 10000)['break_even_attendance'], 500000)

    def test_large_values_stay_exact(self):
        result = run(10 ** 11, 10 ** 6, 10 ** 11, 1)
        self.assertEqual(result['revenue'], 10 ** 17)
        self.assertEqual(result['profit'], 10 ** 17 - 10 ** 11 - 10 ** 6)
        self.assertEqual(result['break_even_attendance'], 2)


class SimulatorApiTestCase(ApiTestCase):
    BODY = {'ticket_price': 50000, 'expected_attendance': 60, 'fixed_costs': 1000000, 'variable_cost_per_head': 10000}

    def setUp(self):
        super().setUp()
        self.manager = self.make_role_user('event_manager')
        self.login_as(self.manager)

    def post(self, **overrides):
        body = {**self.BODY, **overrides}
        return self.client.post(SIMULATOR, {k: v for k, v in body.items() if v != 'OMIT'}, format='json')


class SimulatorApiTests(SimulatorApiTestCase):
    def test_returns_break_even_and_profit(self):
        response = self.post()

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), {
            'inputs': self.BODY,
            'margin_per_head': 40000, 'break_even_attendance': 25,
            'revenue': 3000000, 'costs': 1600000, 'profit': 1400000, 'breaks_even': True,
            'event': None, 'forecast_vs_actual': None,
        })

    def test_zero_margin_is_a_clear_400(self):
        response = self.post(ticket_price=10000, variable_cost_per_head=10000)
        body = self.assert_error(response, 400, 'validation_error', field='ticket_price')
        self.assertEqual(self.field_codes(body), {('ticket_price', 'no_break_even')})
        self.assertIn('never break even', body['message'])

    def test_price_below_cost_per_head_is_a_clear_400(self):
        response = self.post(ticket_price=5000, variable_cost_per_head=10000)
        self.assert_error(response, 400, 'validation_error', field='ticket_price')

    def test_zero_values_that_still_have_a_margin_are_accepted(self):
        response = self.post(expected_attendance=0, fixed_costs=0, variable_cost_per_head=0)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual((response.json()['break_even_attendance'], response.json()['profit']), (0, 0))

    def test_invalid_inputs_are_refused_field_by_field(self):
        cases = [
            ('ticket_price', -1), ('ticket_price', 'cheap'), ('ticket_price', 10.5), ('ticket_price', None),
            ('ticket_price', 'OMIT'), ('ticket_price', 10 ** 11 + 1),
            ('expected_attendance', -1), ('expected_attendance', 1_000_001), ('expected_attendance', 'OMIT'),
            ('fixed_costs', -100), ('fixed_costs', 'OMIT'),
            ('variable_cost_per_head', -1), ('variable_cost_per_head', 'OMIT'),
            ('event', 999999), ('event', 'gala'),
        ]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                self.assert_error(self.post(**{field: value}), 400, 'validation_error', field=field)

    def test_it_writes_nothing(self):
        event = make_event()
        before = (LedgerEntry.objects.count(), Event.objects.count())
        self.post(event=event.id)
        self.assertEqual((LedgerEntry.objects.count(), Event.objects.count()), before)

    def test_get_is_not_allowed(self):
        self.assert_error(self.client.get(SIMULATOR), 405, 'method_not_allowed')


class ForecastVsActualTests(SimulatorApiTestCase):
    def past_event_with_sales(self):
        now = timezone.now()
        event = make_event(title='Freshers Night', starts_at=now - timedelta(days=5), ends_at=now - timedelta(days=5) + timedelta(hours=3))
        tier = make_tier(event, public_price=30000, member_price=20000, capacity=50)
        buyer = self.make_user()
        tickets = purchase_tickets(user=buyer, tier_id=tier.id, quantity=4, outcome='success', idempotency_key='sim-past-key-1').tickets
        for ticket in tickets[:3]:
            scan(operator=self.manager, token=ticket.qr_token)
        post_entry(description='Sound', source_type='expense_request', source_id=1, kind='expense_approved',
                   event=event, lines=[('5000', 50000, 0), ('2000', 0, 50000)])
        return event

    def test_ended_event_gets_forecast_beside_actual(self):
        event = self.past_event_with_sales()

        body = self.post(event=event.id, ticket_price=30000, expected_attendance=10, fixed_costs=40000, variable_cost_per_head=0).json()

        self.assertEqual(body['event'], {'id': event.id, 'title': 'Freshers Night'})
        self.assertEqual(body['forecast_vs_actual'], {
            'forecast': {'attendance': 10, 'revenue': 300000, 'costs': 40000, 'profit': 260000},
            'actual': {'attendance': 3, 'tickets_sold': 4, 'revenue': 120000, 'costs': 50000, 'profit': 70000},
            'difference': {'attendance': -7, 'revenue': -180000, 'costs': 10000, 'profit': -190000},
        })

    def test_actual_matches_the_event_pnl_endpoint(self):
        event = self.past_event_with_sales()
        actual = self.post(event=event.id).json()['forecast_vs_actual']['actual']
        pnl = self.client.get(f'/api/events/{event.id}/pnl').json()
        self.assertEqual((actual['revenue'], actual['costs'], actual['profit']),
                         (pnl['revenue']['total'], pnl['expenses']['total'], pnl['profit']))
        self.assertEqual((actual['attendance'], actual['tickets_sold']), (pnl['attendance']['checked_in'], pnl['attendance']['sold']))

    def test_upcoming_event_has_no_actual_yet(self):
        event = make_event()
        body = self.post(event=event.id).json()
        self.assertEqual(body['event']['id'], event.id)
        self.assertIsNone(body['forecast_vs_actual'])
        self.assertEqual(body['break_even_attendance'], 25)

    def test_ended_event_with_no_activity_reports_zeros(self):
        now = timezone.now()
        event = make_event(starts_at=now - timedelta(days=2), ends_at=now - timedelta(days=1))
        actual = self.post(event=event.id).json()['forecast_vs_actual']['actual']
        self.assertEqual(actual, {'attendance': 0, 'tickets_sold': 0, 'revenue': 0, 'costs': 0, 'profit': 0})


class SimulatorPermissionTests(SimulatorApiTestCase):
    def test_event_manager_treasurer_and_president_may_use_it(self):
        for role in ['treasurer', 'president']:
            self.login_as(self.make_role_user(role))
            self.assertEqual(self.post().status_code, 200)
        self.login_as(self.manager)
        self.assertEqual(self.post().status_code, 200)

    def test_everyone_else_is_refused(self):
        refused = [self.make_role_user('volunteer_coordinator'), self.make_role_user('member'), self.make_user()]
        for user in refused:
            with self.subTest(user=user.email):
                self.login_as(user)
                self.assert_error(self.post(), 403, 'permission_denied')
        self.client.credentials()
        self.assert_error(self.post(), 401, 'not_authenticated')

    def test_event_manager_whose_term_ended_is_refused(self):
        former = self.make_user(email='former@example.com', name='Former', college_id='SSA-F')
        self.give_role(former, 'event_manager', start_offset=-400, end_offset=-1)
        self.login_as(former)
        self.assert_error(self.post(), 403, 'permission_denied')
