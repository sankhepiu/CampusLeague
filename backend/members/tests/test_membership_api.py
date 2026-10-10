from datetime import timedelta
from unittest import mock

from django.utils import timezone

from common.testing import PASSWORD, ApiTestCase
from finance.models import LedgerEntry, LedgerLine
from finance.services import account_balance
from members.models import Membership
from members.services import add_months
from members.tests.test_services import make_plan
from shop.models import Order, OrderLine, Payment

PLANS = '/api/plans'
MEMBERSHIPS = '/api/memberships'
MY_MEMBERSHIP = '/api/memberships/me'
ME = '/api/auth/me'

KEY = 'purchase-key-0001'
OTHER_KEY = 'purchase-key-0002'


class PurchaseTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        self.plan = make_plan(name='Basic', price=50000, duration_months=12, merch_discount_pct=10)
        self.user = self.make_user()
        self.login_as(self.user)

    def buy(self, key=KEY, **body):
        body.setdefault('plan', self.plan.id)
        headers = {'Idempotency-Key': key} if key is not None else {}
        return self.client.post(MEMBERSHIPS, body, format='json', headers=headers)

    def counts(self):
        return {
            'orders': Order.objects.count(),
            'lines': OrderLine.objects.count(),
            'payments': Payment.objects.count(),
            'memberships': Membership.objects.count(),
            'entries': LedgerEntry.objects.count(),
            'ledger_lines': LedgerLine.objects.count(),
        }

    NOTHING = {'orders': 0, 'lines': 0, 'payments': 0, 'memberships': 0, 'entries': 0, 'ledger_lines': 0}
    ONE_PURCHASE = {'orders': 1, 'lines': 1, 'payments': 1, 'memberships': 1, 'entries': 1, 'ledger_lines': 2}


class PlanListTests(ApiTestCase):
    def test_public_list_of_active_plans_cheapest_first(self):
        plus = make_plan(name='Plus', price=90000, ticket_discount_pct=5, merch_discount_pct=20)
        basic = make_plan(name='Basic', price=50000)
        make_plan(name='Retired', price=10000, active=False)

        response = self.client.get(PLANS)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), {
            'count': 2,
            'next': None,
            'previous': None,
            'results': [
                {
                    'id': basic.id, 'name': 'Basic', 'price': 50000, 'duration_months': 12,
                    'ticket_discount_pct': 0, 'merch_discount_pct': 10,
                },
                {
                    'id': plus.id, 'name': 'Plus', 'price': 90000, 'duration_months': 12,
                    'ticket_discount_pct': 5, 'merch_discount_pct': 20,
                },
            ],
        })

    def test_list_is_paginated_at_20(self):
        for number in range(21):
            make_plan(name=f'Plan {number:02}', price=1000 + number)

        first = self.client.get(PLANS).json()
        second = self.client.get(PLANS, {'page': 2}).json()

        self.assertEqual(first['count'], 21)
        self.assertEqual(len(first['results']), 20)
        self.assertIsNotNone(first['next'])
        self.assertEqual(len(second['results']), 1)

    def test_plans_cannot_be_created_through_the_api(self):
        self.login_as(self.make_user())
        response = self.client.post(PLANS, {'name': 'Free', 'price': 1}, format='json')
        self.assert_error(response, 405, 'method_not_allowed')


class SuccessfulPurchaseTests(PurchaseTestCase):
    def test_response_describes_order_payment_and_membership(self):
        response = self.buy()

        self.assertEqual(response.status_code, 201, response.content)
        order, payment, membership = Order.objects.get(), Payment.objects.get(), Membership.objects.get()
        body = response.json()
        self.assertEqual(set(body), {'order', 'payment', 'membership'})
        self.assertEqual(body['order']['id'], order.id)
        self.assertEqual(body['order']['status'], 'paid')
        self.assertEqual(
            (body['order']['subtotal'], body['order']['discount'], body['order']['total']),
            (50000, 0, 50000),
        )
        self.assertEqual(body['order']['payment_ref'], payment.gateway_ref)
        self.assertEqual(body['order']['lines'], [{
            'id': OrderLine.objects.get().id, 'kind': 'membership',
            'plan': self.plan.id, 'tier': None, 'product_size': None,
            'qty': 1, 'unit_price': 50000, 'discount': 0,
        }])
        self.assertEqual(body['payment']['amount'], 50000)
        self.assertEqual(body['payment']['status'], 'succeeded')
        self.assertTrue(body['payment']['gateway_ref'].startswith('mock_'))
        self.assertNotIn('idempotency_key', body['payment'])
        self.assertEqual(body['membership'], {
            'id': membership.id,
            'plan': {
                'id': self.plan.id, 'name': 'Basic', 'price': 50000, 'duration_months': 12,
                'ticket_discount_pct': 0, 'merch_discount_pct': 10,
            },
            'status': 'active',
            'start_date': self.today.isoformat(),
            'end_date': add_months(self.today, 12).isoformat(),
        })

    def test_database_rows_are_linked_to_the_buyer(self):
        self.buy()

        self.assertEqual(self.counts(), self.ONE_PURCHASE)
        order, payment, line = Order.objects.get(), Payment.objects.get(), OrderLine.objects.get()
        self.assertEqual(order.buyer, self.user)
        self.assertEqual(payment.order, order)
        self.assertEqual(payment.idempotency_key, KEY)
        self.assertEqual(line.membership, Membership.objects.get())
        self.assertEqual(line.membership.user, self.user)

    def test_dues_are_posted_to_the_ledger_once_and_balanced(self):
        self.buy()

        entry = LedgerEntry.objects.get()
        payment = Payment.objects.get()
        self.assertEqual(
            (entry.source_type, entry.source_id, entry.kind),
            ('payment', payment.id, 'membership_dues'),
        )
        self.assertEqual(entry.created_by, self.user)
        self.assertEqual(
            sorted(entry.lines.values_list('account__code', 'debit', 'credit')),
            [('1000', 50000, 0), ('4000', 0, 50000)],
        )
        self.assertEqual(account_balance('1000'), 50000)
        self.assertEqual(account_balance('4000'), 50000)

    def test_user_shows_as_active_afterwards(self):
        self.assertEqual(self.client.get(ME).json()['membership_status'], 'none')

        self.buy()

        self.assertEqual(self.client.get(ME).json()['membership_status'], 'active')
        mine = self.client.get(MY_MEMBERSHIP).json()
        self.assertEqual(mine['status'], 'active')
        self.assertEqual(mine['membership']['plan']['merch_discount_pct'], 10)
        self.assertEqual(mine['paid_until'], add_months(self.today, 12).isoformat())

    def test_price_and_buyer_sent_by_the_client_are_ignored(self):
        other = self.make_user(email='ravi@example.com', name='Ravi', college_id='SSA-002')

        response = self.buy(
            price=1, unit_price=1, total=1, subtotal=1, discount=49999, amount=1,
            user=other.id, buyer=other.id, status='active', end_date='2099-01-01',
        )

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(Order.objects.get().total, 50000)
        self.assertEqual(Order.objects.get().buyer, self.user)
        self.assertEqual(Payment.objects.get().amount, 50000)
        self.assertEqual(account_balance('4000'), 50000)
        self.assertEqual(Membership.objects.get().user, self.user)
        self.assertEqual(Membership.objects.get().end_date, add_months(self.today, 12))

    def test_price_is_read_from_the_plan_at_purchase_time(self):
        self.plan.price = 60000
        self.plan.save()
        self.buy()
        self.assertEqual(Payment.objects.get().amount, 60000)
        self.assertEqual(account_balance('1000'), 60000)

    def test_renewal_with_a_new_key_extends_cover_and_posts_a_second_entry(self):
        self.buy(key=KEY)
        response = self.buy(key=OTHER_KEY)

        self.assertEqual(response.status_code, 201, response.content)
        first, second = Membership.objects.order_by('start_date')
        self.assertEqual(second.start_date, first.end_date + timedelta(days=1))
        self.assertEqual(LedgerEntry.objects.count(), 2)
        self.assertEqual(account_balance('1000'), 100000)
        self.assertEqual(self.client.get(MY_MEMBERSHIP).json()['paid_until'], second.end_date.isoformat())

    def test_two_users_each_get_their_own_membership(self):
        self.buy(key=KEY)
        other = self.make_user(email='ravi@example.com', name='Ravi', college_id='SSA-002')
        self.login_as(other)

        response = self.buy(key=OTHER_KEY)

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(Membership.objects.get(user=other).start_date, self.today)
        self.assertEqual(account_balance('4000'), 100000)


class IdempotencyTests(PurchaseTestCase):
    """Plan: "Replay the same payment request; one entry, one charge"."""

    def test_replay_returns_the_first_result_and_creates_nothing(self):
        first = self.buy()
        replay = self.buy()

        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 200, replay.content)
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(self.counts(), self.ONE_PURCHASE)
        self.assertEqual(account_balance('1000'), 50000)

    def test_many_replays_still_charge_once(self):
        for _ in range(5):
            self.buy()
        self.assertEqual(self.counts(), self.ONE_PURCHASE)
        self.assertEqual(account_balance('4000'), 50000)

    def test_key_is_required(self):
        self.assert_error(self.buy(key=None), 400, 'idempotency_key_required')
        self.assertEqual(self.counts(), self.NOTHING)

    def test_malformed_keys_are_refused(self):
        for key in ['short', 'has spaces in it', 'x' * 65, 'semi;colon-key']:
            with self.subTest(key=key):
                self.assert_error(self.buy(key=key), 400, 'idempotency_key_required')
        self.assertEqual(self.counts(), self.NOTHING)

    def test_key_length_boundaries_are_accepted(self):
        self.assertEqual(self.buy(key='a' * 8).status_code, 201)
        self.assertEqual(self.buy(key='b' * 64).status_code, 201)

    def test_another_user_cannot_replay_someone_elses_key(self):
        first = self.buy()
        other = self.make_user(email='ravi@example.com', name='Ravi', college_id='SSA-002')
        self.login_as(other)

        response = self.buy()

        self.assert_error(response, 409, 'idempotency_key_reused')
        self.assertNotIn(str(first.json()['order']['id']), response.content.decode())
        self.assertEqual(self.counts(), self.ONE_PURCHASE)
        self.assertEqual(Membership.objects.filter(user=other).count(), 0)

    def test_same_key_for_a_different_plan_is_a_conflict(self):
        plus = make_plan(name='Plus', price=90000)
        self.buy()

        response = self.buy(plan=plus.id)

        self.assert_error(response, 409, 'idempotency_key_reused')
        self.assertEqual(self.counts(), self.ONE_PURCHASE)
        self.assertEqual(account_balance('1000'), 50000)


class FailedAndPendingPaymentTests(PurchaseTestCase):
    def test_failure_cancels_the_order_and_creates_nothing_else(self):
        response = self.buy(test_outcome='failure')

        self.assert_error(response, 402, 'payment_failed')
        self.assertEqual(self.counts(), {**self.NOTHING, 'orders': 1, 'lines': 1})
        self.assertEqual(Order.objects.get().status, 'cancelled')
        self.assertEqual(Order.objects.get().payment_ref, '')
        self.assertEqual(account_balance('1000'), 0)
        self.assertEqual(self.client.get(ME).json()['membership_status'], 'none')

    def test_pending_leaves_the_order_pending_and_creates_nothing_else(self):
        response = self.buy(test_outcome='pending')

        self.assertEqual(response.status_code, 202, response.content)
        body = response.json()
        self.assertEqual(body['order']['status'], 'pending')
        self.assertIsNone(body['payment'])
        self.assertIsNone(body['membership'])
        self.assertEqual(self.counts(), {**self.NOTHING, 'orders': 1, 'lines': 1})
        self.assertEqual(account_balance('1000'), 0)
        self.assertEqual(self.client.get(ME).json()['membership_status'], 'none')

    def test_failed_key_can_be_retried_and_then_succeeds_once(self):
        self.buy(test_outcome='failure')

        response = self.buy(test_outcome='success')

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(sorted(Order.objects.values_list('status', flat=True)), ['cancelled', 'paid'])
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(LedgerEntry.objects.count(), 1)
        self.assertEqual(account_balance('1000'), 50000)

    def test_ledger_failure_rolls_back_the_whole_purchase(self):
        # Plan: "Post the ledger entry in the same transaction as the thing
        # that caused it. If one fails, both roll back."
        with mock.patch('shop.payments.post_entry', side_effect=RuntimeError('ledger down')):
            with self.assertLogs('campusleague.api', level='ERROR'):
                response = self.buy()

        self.assert_error(response, 500, 'server_error')
        self.assertNotIn('ledger down', response.content.decode())
        self.assertEqual(self.counts(), self.NOTHING)
        self.assertEqual(self.client.get(ME).json()['membership_status'], 'none')

    def test_purchase_works_again_after_a_rolled_back_attempt(self):
        with mock.patch('shop.payments.post_entry', side_effect=RuntimeError('ledger down')):
            with self.assertLogs('campusleague.api', level='ERROR'):
                self.buy()

        self.assertEqual(self.buy().status_code, 201)
        self.assertEqual(self.counts(), self.ONE_PURCHASE)


class PurchaseValidationTests(PurchaseTestCase):
    def test_requires_login(self):
        self.client.credentials()
        self.assert_error(self.buy(), 401, 'not_authenticated')
        self.assertEqual(self.counts(), self.NOTHING)

    def test_plan_is_required(self):
        response = self.client.post(MEMBERSHIPS, {}, format='json', headers={'Idempotency-Key': KEY})
        body = self.assert_error(response, 400, 'validation_error', field='plan')
        self.assertEqual(self.field_codes(body), {('plan', 'required')})

    def test_unknown_plan_is_refused(self):
        body = self.assert_error(self.buy(plan=999999), 400, 'validation_error', field='plan')
        self.assertEqual(self.field_codes(body), {('plan', 'does_not_exist')})
        self.assertEqual(self.counts(), self.NOTHING)

    def test_inactive_plan_is_refused(self):
        self.plan.active = False
        self.plan.save()
        body = self.assert_error(self.buy(), 400, 'validation_error', field='plan')
        self.assertEqual(self.field_codes(body), {('plan', 'does_not_exist')})
        self.assertEqual(self.counts(), self.NOTHING)

    def test_wrong_type_for_plan_is_refused(self):
        for bad in ['basic', None, [1], {'id': 1}, -1, 1.5]:
            with self.subTest(plan=bad):
                self.assert_error(self.buy(plan=bad), 400, 'validation_error', field='plan')
        self.assertEqual(self.counts(), self.NOTHING)

    def test_unknown_outcome_is_refused(self):
        body = self.assert_error(
            self.buy(test_outcome='free'), 400, 'validation_error', field='test_outcome',
        )
        self.assertEqual(self.field_codes(body), {('test_outcome', 'invalid_choice')})
        self.assertEqual(self.counts(), self.NOTHING)

    def test_get_is_not_allowed(self):
        self.assert_error(self.client.get(MEMBERSHIPS), 405, 'method_not_allowed')


class MyMembershipTests(PurchaseTestCase):
    def test_requires_login(self):
        self.client.credentials()
        self.assert_error(self.client.get(MY_MEMBERSHIP), 401, 'not_authenticated')

    def test_user_without_membership(self):
        self.assertEqual(
            self.client.get(MY_MEMBERSHIP).json(),
            {'status': 'none', 'membership': None, 'paid_until': None},
        )

    def test_lapsed_member(self):
        Membership.objects.create(
            user=self.user, plan=self.plan, status='active',
            start_date=self.today - timedelta(days=400), end_date=self.today - timedelta(days=1),
        )
        self.assertEqual(
            self.client.get(MY_MEMBERSHIP).json(),
            {'status': 'lapsed', 'membership': None, 'paid_until': None},
        )
        self.assertEqual(self.client.get(ME).json()['membership_status'], 'lapsed')

    def test_shows_only_my_own_membership(self):
        other = self.make_user(email='ravi@example.com', name='Ravi', college_id='SSA-002')
        Membership.objects.create(
            user=other, plan=self.plan, status='active',
            start_date=self.today, end_date=self.today + timedelta(days=30),
        )
        self.assertEqual(self.client.get(MY_MEMBERSHIP, {'user': other.id}).json()['status'], 'none')


class Phase1JourneyTests(ApiTestCase):
    """Plan, Phase 1 "done when": "A new person signs up, buys a plan, shows
    active, and the dues appear in the ledger." Every step goes through HTTP.
    """

    def test_new_person_signs_up_buys_a_plan_and_the_dues_reach_the_ledger(self):
        make_plan(name='Plus', price=90000)
        make_plan(name='Basic', price=50000)

        # Priya, not logged in, looks at the plans.
        plans = self.client.get(PLANS).json()['results']
        basic = next(plan for plan in plans if plan['name'] == 'Basic')

        # She signs up and is logged in by the returned token.
        signup = self.client.post('/api/auth/signup', {
            'email': 'priya@example.com', 'password': PASSWORD,
            'name': 'Priya', 'college_id': 'SSA-041',
        }, format='json')
        self.assertEqual(signup.status_code, 201, signup.content)
        self.assertEqual(signup.json()['user']['membership_status'], 'none')
        self.use_token(signup.json()['token'])

        # She buys the Basic plan.
        purchase = self.client.post(
            MEMBERSHIPS, {'plan': basic['id']}, format='json', headers={'Idempotency-Key': KEY},
        )
        self.assertEqual(purchase.status_code, 201, purchase.content)

        # She shows as active.
        self.assertEqual(self.client.get(ME).json()['membership_status'], 'active')
        self.assertEqual(self.client.get(MY_MEMBERSHIP).json()['status'], 'active')

        # The dues are in the ledger, traceable back to her payment.
        entry = LedgerEntry.objects.get()
        payment = Payment.objects.get(pk=entry.source_id)
        self.assertEqual(payment.order.buyer.email, 'priya@example.com')
        self.assertEqual(payment.amount, basic['price'])
        self.assertEqual(account_balance('1000'), 50000)
        self.assertEqual(account_balance('4000'), 50000)
