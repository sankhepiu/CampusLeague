from datetime import timedelta

from django.utils import timezone

from common.testing import ApiTestCase
from events.models import Event, Ticket
from events.tests.helpers import make_event, make_member, make_tier
from events.tickets import scan
from finance import expenses
from finance.models import ExpenseRequest
from insights import health
from members.models import Membership
from shop.payments import purchase_tickets
from volunteering.models import Fundraiser, Task

HEALTH = '/api/health'


class HealthTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.president = self.make_role_user('president')
        self.login_as(self.president)
        self.count = 0

    def person(self, name):
        self.count += 1
        return self.make_user(email=f'p{self.count}@example.com', name=name, college_id=f'P{self.count}')

    def components(self):
        response = self.client.get(HEALTH)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        return body, {component['key']: component for component in body['components']}


class HandComputedHealthTests(HealthTestCase):
    """A small club where every figure can be worked out by hand."""

    def setUp(self):
        super().setUp()
        # Membership: 5 people have ever joined.
        for name in ['A', 'B', 'C']:
            make_member(self.person(name))                    # active, never lapsed
        make_member(self.person('D'), days_left=-10)          # ran out, not renewed
        renewed = self.person('E')
        make_member(renewed, days_left=-40)                   # ran out...
        make_member(renewed, days_left=300)                   # ...and renewed
        #   active 4 of 5 = 80%.  renewed 1 of 2 (D, E) = 50%.
        #   score = (70*80 + 30*50) / 100 = 71

        # Attendance: one closed event, 4 sold, 3 checked in = 75.
        buyer = self.person('Buyer')                          # not a member: pays 80000
        closed = make_event(title='Closed')
        closed_tier = make_tier(closed)
        sold = purchase_tickets(user=buyer, tier_id=closed_tier.id, quantity=4, outcome='success', idempotency_key='health-key-01').tickets
        for ticket in sold[:3]:
            scan(operator=self.president, token=ticket.qr_token)
        Event.objects.filter(pk=closed.pk).update(status='closed')
        # An event still on sale: its unscanned ticket must NOT count.
        open_tier = make_tier(make_event(title='Open'))
        purchase_tickets(user=buyer, tier_id=open_tier.id, quantity=1, outcome='success', idempotency_key='health-key-02')

        # Volunteering: 4 tasks, 1 done = 25.
        fundraiser = Fundraiser.objects.create(title='Bake Sale', goal_amount=1000, starts_on='2026-10-01', ends_on='2026-10-31')
        for status in ['done', 'doing', 'todo', 'todo']:
            Task.objects.create(fundraiser=fundraiser, title=f'Task {status}', status=status)

        # Money: cash in 5 tickets x 80000 = 400000; cash out one payout of 100000.
        #   400000 / (400000 + 100000) = 80
        treasurer = self.make_role_user('treasurer')
        expense = ExpenseRequest.objects.create(
            requester=buyer, amount=100000, category='event', event=closed, description='Hall', receipt_file='receipts/t.png',
        )
        expenses.approve(expense.pk, treasurer)
        expenses.mark_paid(expense.pk, self.president)
        # An approved-but-unpaid expense moves no cash, so it must not count.
        owed = ExpenseRequest.objects.create(
            requester=buyer, amount=999999, category='event', event=closed, description='Later', receipt_file='receipts/t.png',
        )
        expenses.approve(owed.pk, treasurer)

    def test_each_component_matches_the_hand_calculation(self):
        body, parts = self.components()

        self.assertEqual({key: part['score'] for key, part in parts.items()},
                         {'membership': 71, 'attendance': 75, 'volunteering': 25, 'money': 80})
        self.assertEqual({key: part['weight'] for key, part in parts.items()},
                         {'membership': 30, 'attendance': 25, 'volunteering': 20, 'money': 25})
        # (71*30 + 75*25 + 25*20 + 80*25) / 100 = 6505 / 100 = 65.05 -> 65
        self.assertEqual(body['score'], 65)
        self.assertEqual({key: part['contribution'] for key, part in parts.items()},
                         {'membership': 21.3, 'attendance': 18.8, 'volunteering': 5.0, 'money': 20.0})

    def test_each_reason_quotes_the_real_numbers(self):
        _, parts = self.components()
        self.assertEqual(parts['membership']['reason'],
                         '4 of 5 people who joined are active members (80%); 1 of 2 whose membership ran out have renewed (50%).')
        self.assertEqual(parts['attendance']['reason'], '3 of 4 tickets were checked in across 1 closed event(s).')
        self.assertEqual(parts['volunteering']['reason'], '1 of 4 tasks are done.')
        self.assertEqual(parts['money']['reason'],
                         'In the last 30 days Rs 4,000.00 came in and Rs 1,000.00 went out; cash is now Rs 3,000.00.')

    def test_response_shape(self):
        body, _ = self.components()
        self.assertEqual(set(body), {'score', 'components'})
        self.assertEqual([c['key'] for c in body['components']], ['membership', 'attendance', 'volunteering', 'money'])
        self.assertEqual(set(body['components'][0]), {'key', 'label', 'score', 'weight', 'contribution', 'reason'})

    def test_score_moves_when_the_underlying_facts_change(self):
        Task.objects.filter(status='todo').update(status='done')          # 3 of 4 done -> 75
        Ticket.objects.filter(status='valid', event__status='closed').update(status='cancelled')   # 3 of 3 -> 100
        body, parts = self.components()
        self.assertEqual((parts['volunteering']['score'], parts['attendance']['score']), (75, 100))
        # (71*30 + 100*25 + 75*20 + 80*25) / 100 = 81.3 -> 81
        self.assertEqual(body['score'], 81)

    def test_cash_movements_older_than_the_window_are_ignored(self):
        later = timezone.now() + timedelta(days=health.CASH_TREND_DAYS + 1)
        result = {c['key']: c for c in health.club_health(now=later)['components']}
        self.assertIsNone(result['money']['score'])
        self.assertEqual(result['money']['reason'], 'No cash has moved in the last 30 days.')

    def test_cancelled_and_pending_memberships_are_not_counted(self):
        Membership.objects.create(
            user=self.person('F'), plan=Membership.objects.first().plan, status='cancelled',
            start_date=timezone.localdate(), end_date=timezone.localdate(),
        )
        _, parts = self.components()
        self.assertIn('4 of 5', parts['membership']['reason'])


class WeightsTests(HealthTestCase):
    def test_weights_sum_to_100(self):
        self.assertEqual(sum(health.WEIGHTS.values()), 100)
        self.assertEqual(health.MEMBERSHIP_ACTIVE_SHARE_WEIGHT + health.MEMBERSHIP_RENEWAL_WEIGHT, 100)

    def test_percentage_rounds_halves_up(self):
        self.assertEqual([health.pct(1, 8), health.pct(1, 3), health.pct(2, 3), health.pct(0, 5), health.pct(5, 5)],
                         [13, 33, 67, 0, 100])        # 12.5 -> 13


class EmptyAndPartialClubTests(HealthTestCase):
    def test_brand_new_club_has_no_score_and_says_why(self):
        body, parts = self.components()
        self.assertIsNone(body['score'])
        self.assertEqual({key: part['score'] for key, part in parts.items()},
                         {'membership': None, 'attendance': None, 'volunteering': None, 'money': None})
        self.assertEqual(parts['membership']['reason'], 'Nobody has joined yet.')
        self.assertEqual(parts['attendance']['reason'], 'No closed event has sold tickets yet.')
        self.assertEqual(parts['volunteering']['reason'], 'No tasks have been created yet.')
        self.assertTrue(all(part['contribution'] is None for part in parts.values()))

    def test_missing_components_are_left_out_of_the_average(self):
        make_member(self.person('A'))
        make_member(self.person('B'), days_left=-5)        # 1 of 2 active = 50; 0 of 1 renewed -> (70*50)/100 = 35
        fundraiser = Fundraiser.objects.create(title='F', goal_amount=1000, starts_on='2026-10-01', ends_on='2026-10-31')
        Task.objects.create(fundraiser=fundraiser, title='Done', status='done')     # 100

        body, parts = self.components()

        self.assertEqual((parts['membership']['score'], parts['volunteering']['score']), (35, 100))
        self.assertIsNone(parts['attendance']['score'])
        # Only membership (30) and volunteering (20) count: (35*30 + 100*20) / 50 = 61
        self.assertEqual(body['score'], 61)
        self.assertEqual((parts['membership']['contribution'], parts['volunteering']['contribution']), (21.0, 40.0))

    def test_renewals_not_scored_until_a_membership_has_run_out(self):
        make_member(self.person('A'))
        _, parts = self.components()
        self.assertEqual(parts['membership']['score'], 100)
        self.assertIn('renewals are not scored', parts['membership']['reason'])

    def test_all_zero_scores_give_zero_not_an_error(self):
        make_member(self.person('A'), days_left=-5)        # 0 of 1 active, 0 of 1 renewed
        body, parts = self.components()
        self.assertEqual((parts['membership']['score'], body['score']), (0, 0))


class HealthPermissionTests(HealthTestCase):
    def test_only_the_president_may_read_it(self):
        for role in ['treasurer', 'event_manager', 'volunteer_coordinator', 'member']:
            with self.subTest(role=role):
                self.login_as(self.make_role_user(role))
                self.assert_error(self.client.get(HEALTH), 403, 'permission_denied')
        self.login_as(self.make_user())
        self.assert_error(self.client.get(HEALTH), 403, 'permission_denied')
        self.client.credentials()
        self.assert_error(self.client.get(HEALTH), 401, 'not_authenticated')

    def test_former_president_is_refused(self):
        former = self.make_user(email='former@example.com', name='Former', college_id='SSA-F')
        self.give_role(former, 'president', start_offset=-400, end_offset=-1)
        self.login_as(former)
        self.assert_error(self.client.get(HEALTH), 403, 'permission_denied')

    def test_it_is_read_only(self):
        self.assert_error(self.client.post(HEALTH, {}, format='json'), 405, 'method_not_allowed')
