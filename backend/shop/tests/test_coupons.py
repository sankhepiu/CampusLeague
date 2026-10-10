import threading
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from common.testing import ApiTestCase
from events.models import Ticket
from events.tests.helpers import make_event, make_member, make_tier
from finance import reports
from finance.models import LedgerLine
from finance.services import account_balance
from members.models import Membership, MembershipPlan
from shop import coupons
from shop.models import Coupon, CouponRedemption, Order, OrderLine, Payment
from shop.payments import purchase_membership
from shop.tests.helpers import make_product, size_of
from shop.tests.test_razorpay import RAZORPAY_ON, FakeRazorpay, sign

User = get_user_model()

VALIDATE = '/api/coupons/validate'
COUPONS = '/api/coupons'


def make_coupon(code='SAVE10', **fields):
    defaults = {'kind': 'percent', 'value': 10, 'applies_to': 'all'}
    defaults.update(fields)
    return Coupon.objects.create(code=code, **defaults)


class CouponTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.login_as(self.user)
        self.plan = MembershipPlan.objects.create(name='Basic', price=50000, duration_months=12)
        self.keys = 0

    def key(self):
        self.keys += 1
        return f'coupon-key-{self.keys:04}'

    def buy_membership(self, coupon=None, **body):
        if coupon is not None:
            body['coupon'] = coupon
        return self.client.post(
            '/api/memberships', {'plan': self.plan.pk, **body}, format='json', HTTP_IDEMPOTENCY_KEY=self.key(),
        )

    def assert_reconciles(self):
        result = reports.reconcile()
        self.assertEqual(len(result['checks']), 11)
        self.assertTrue(result['ok'], [check for check in result['checks'] if not check['ok']])


class ValidateEndpointTests(CouponTestCase):
    def check(self, code='SAVE10', applies_to='membership', amount=50000):
        response = self.client.post(VALIDATE, {'code': code, 'applies_to': applies_to, 'amount': amount}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_valid_percent_coupon(self):
        make_coupon()
        self.assertEqual(self.check(), {
            'valid': True, 'discount': 5000, 'final_amount': 45000, 'reason': None, 'message': None,
        })

    def test_code_is_case_insensitive_and_trimmed(self):
        make_coupon()
        for code in ['save10', 'Save10', ' SAVE10 ']:
            self.assertTrue(self.check(code=code)['valid'], code)

    def test_flat_coupon_and_cap(self):
        make_coupon('FLAT', kind='flat', value=7500)
        self.assertEqual(self.check('FLAT')['discount'], 7500)
        make_coupon('CAPPED', value=50, max_discount=10000)
        self.assertEqual((self.check('CAPPED')['discount'], self.check('CAPPED')['final_amount']), (10000, 40000))
        # Under the cap the percentage applies as it is.
        self.assertEqual(self.check('CAPPED', amount=10000)['discount'], 5000)

    def test_percentage_is_rounded_down(self):
        make_coupon('THIRD', value=33)
        self.assertEqual(self.check('THIRD', amount=999)['discount'], 329)       # 329.67

    def test_a_coupon_never_makes_the_order_free(self):
        make_coupon('ALL', value=100)
        make_coupon('BIG', kind='flat', value=1_000_000)
        for code in ['ALL', 'BIG']:
            body = self.check(code)
            self.assertEqual((body['valid'], body['discount'], body['final_amount']), (True, 49900, 100), code)

    def test_every_reason(self):
        now = timezone.now()
        make_coupon('OFF', active=False)
        make_coupon('SOON', valid_from=now + timedelta(days=1))
        make_coupon('OLD', valid_to=now - timedelta(seconds=1))
        make_coupon('MERCH', applies_to='merch')
        make_coupon('BIGSPEND', min_order=50001)
        make_coupon('GONE', usage_limit=2, used_count=2)
        make_coupon('TINY', kind='flat', value=50)
        used = make_coupon('USED')
        order = Order.objects.create(buyer=self.user, subtotal=100, total=100)
        CouponRedemption.objects.create(coupon=used, user=self.user, order=order, discount=10)

        cases = [
            ('NOSUCH', 50000, 'not_found'), ('OFF', 50000, 'inactive'), ('SOON', 50000, 'not_started'),
            ('OLD', 50000, 'expired'), ('MERCH', 50000, 'not_applicable'), ('BIGSPEND', 50000, 'min_order_not_met'),
            ('GONE', 50000, 'usage_limit_reached'), ('USED', 50000, 'already_used'), ('TINY', 100, 'no_discount'),
        ]
        for code, amount, reason in cases:
            with self.subTest(code=code):
                body = self.check(code, amount=amount)
                self.assertEqual((body['valid'], body['discount'], body['final_amount'], body['reason']),
                                 (False, 0, amount, reason))
                self.assertTrue(body['message'])
        # On its boundaries the coupon is accepted.
        self.assertTrue(self.check('BIGSPEND', amount=50001)['valid'])
        make_coupon('NOW', valid_from=now - timedelta(seconds=1), valid_to=now + timedelta(days=1))
        self.assertTrue(self.check('NOW')['valid'])

    def test_validating_changes_nothing(self):
        coupon = make_coupon(usage_limit=1)
        for _ in range(3):
            self.assertTrue(self.check()['valid'])
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 0)
        self.assertEqual(CouponRedemption.objects.count(), 0)

    def test_bad_requests(self):
        make_coupon()
        for body, field in [
            ({'applies_to': 'membership', 'amount': 100}, 'code'),
            ({'code': 'SAVE10', 'amount': 100}, 'applies_to'),
            ({'code': 'SAVE10', 'applies_to': 'all', 'amount': 100}, 'applies_to'),
            ({'code': 'SAVE10', 'applies_to': 'membership'}, 'amount'),
            ({'code': 'SAVE10', 'applies_to': 'membership', 'amount': 0}, 'amount'),
            ({'code': 'SAVE10', 'applies_to': 'membership', 'amount': 1_000_000_001}, 'amount'),
        ]:
            with self.subTest(body=body):
                self.assert_error(self.client.post(VALIDATE, body, format='json'), 400, 'validation_error', field)
        self.client.credentials()
        self.assert_error(self.client.post(VALIDATE, {}, format='json'), 401, 'not_authenticated')


class PurchaseWithCouponTests(CouponTestCase):
    def test_membership_with_a_coupon(self):
        coupon = make_coupon('WELCOME10', applies_to='membership')
        response = self.buy_membership('welcome10')
        self.assertEqual(response.status_code, 201, response.content)
        order = response.json()['order']
        self.assertEqual(
            (order['subtotal'], order['discount'], order['coupon'], order['coupon_discount'], order['total']),
            (50000, 5000, 'WELCOME10', 5000, 45000),
        )
        self.assertEqual((order['lines'][0]['discount'], order['lines'][0]['coupon_discount']), (5000, 5000))
        self.assertEqual(response.json()['payment']['amount'], 45000)
        # Ledger: revenue at the amount actually paid, as before coupons.
        self.assertEqual(sorted(LedgerLine.objects.values_list('account__code', 'debit', 'credit')),
                         [('1000', 45000, 0), ('4000', 0, 45000)])
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 1)
        redemption = CouponRedemption.objects.get()
        self.assertEqual((redemption.coupon, redemption.user, redemption.order_id, redemption.discount),
                         (coupon, self.user, order['id'], 5000))
        self.assert_reconciles()
        # GET /orders/me shows it too.
        listed = self.client.get('/api/orders/me').json()['results'][0]
        self.assertEqual((listed['coupon'], listed['coupon_discount']), ('WELCOME10', 5000))

    def test_no_coupon_or_a_blank_one_changes_nothing(self):
        for coupon in [None, '', '   ']:
            response = self.buy_membership(coupon)
            self.assertEqual(response.status_code, 201, response.content)
            order = response.json()['order']
            self.assertEqual((order['coupon'], order['coupon_discount'], order['discount'], order['total']),
                             (None, 0, 0, 50000))

    def test_an_unusable_coupon_refuses_the_purchase(self):
        make_coupon('MERCHONLY', applies_to='merch')
        make_coupon('OFF', active=False)
        for code in ['NOSUCH', 'MERCHONLY', 'OFF']:
            with self.subTest(code=code):
                self.assert_error(self.buy_membership(code), 400, 'coupon_invalid')
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(Membership.objects.count(), 0)

    def test_tickets_member_price_then_coupon(self):
        tier = make_tier(make_event())            # 80000 public, 60000 member
        make_member(self.user)
        make_coupon('GALA50', kind='flat', value=5000, min_order=20000, applies_to='tickets')
        response = self.client.post(
            f'/api/events/{tier.event_id}/tickets', {'tier': tier.pk, 'quantity': 3, 'coupon': 'GALA50'},
            format='json', HTTP_IDEMPOTENCY_KEY=self.key(),
        )
        self.assertEqual(response.status_code, 201, response.content)
        order = response.json()['order']
        # 3 x member price 60000 = 180000, then 5000 off.
        self.assertEqual((order['subtotal'], order['discount'], order['coupon_discount'], order['total']),
                         (180000, 5000, 5000, 175000))
        # Each ticket records its share of what was paid, rounded down.
        self.assertEqual(set(Ticket.objects.values_list('price_paid', flat=True)), {58333})
        self.assertEqual(account_balance('4100'), 175000)
        self.assert_reconciles()

    def test_ticket_coupon_below_its_minimum_order_is_refused(self):
        tier = make_tier(make_event(), public_price=15000, member_price=15000)
        make_coupon('GALA50', kind='flat', value=5000, min_order=20000, applies_to='tickets')
        response = self.client.post(
            f'/api/events/{tier.event_id}/tickets', {'tier': tier.pk, 'coupon': 'GALA50'},
            format='json', HTTP_IDEMPOTENCY_KEY=self.key(),
        )
        self.assert_error(response, 400, 'coupon_invalid')
        self.assertEqual(Ticket.objects.count(), 0)
        tier.refresh_from_db()
        self.assertEqual(tier.sold_count, 0)

    def test_merch_price_order_is_sale_then_member_then_coupon(self):
        product = make_product(base_price=100000, stock_by_size={'M': 5}, sale_pct=20)
        self.plan.merch_discount_pct = 10
        self.plan.save()
        make_member(self.user)
        make_coupon('MERCH20', value=20, max_discount=15000, applies_to='merch')
        size = size_of(product, 'M')

        # What the catalogue quotes: 100000 -20% = 80000, -10% = 72000.
        listed = self.client.get(f'/api/products/{product.pk}').json()
        self.assertEqual((listed['base_price'], listed['sale_pct'], listed['price']), (100000, 20, 72000))

        response = self.client.post(
            '/api/orders', {'items': [{'product_size': size.pk, 'quantity': 1}], 'coupon': 'MERCH20'},
            format='json', HTTP_IDEMPOTENCY_KEY=self.key(),
        )
        self.assertEqual(response.status_code, 201, response.content)
        order = response.json()['order']
        # Coupon: 20% of 72000 = 14400 (under the 15000 cap). Paid 57600.
        self.assertEqual((order['subtotal'], order['discount'], order['coupon_discount'], order['total']),
                         (100000, 42400, 14400, 57600))
        line = order['lines'][0]
        self.assertEqual((line['unit_price'], line['discount'], line['coupon_discount']), (100000, 42400, 14400))
        self.assertEqual(account_balance('4200'), 57600)
        self.assert_reconciles()

    def test_coupon_is_shared_across_merch_lines_exactly(self):
        product = make_product(base_price=33333, stock_by_size={'S': 5, 'M': 5, 'L': 5})
        make_coupon('FLAT', kind='flat', value=10000, applies_to='merch')
        items = [{'product_size': size_of(product, size).pk, 'quantity': 1} for size in ['S', 'M', 'L']]
        response = self.client.post(
            '/api/orders', {'items': items, 'coupon': 'FLAT'}, format='json', HTTP_IDEMPOTENCY_KEY=self.key(),
        )
        self.assertEqual(response.status_code, 201, response.content)
        order = response.json()['order']
        shares = [line['coupon_discount'] for line in order['lines']]
        # 10000 over three equal lines: 3333, 3333, and the last takes 3334.
        self.assertEqual(sorted(shares), [3333, 3333, 3334])
        self.assertEqual((sum(shares), order['coupon_discount'], order['total']), (10000, 10000, 89999))
        self.assertEqual(sum(line.amount for line in OrderLine.objects.all()), 89999)
        self.assert_reconciles()

    def test_a_coupon_never_makes_a_purchase_free(self):
        make_coupon('ALL', value=100)
        response = self.buy_membership('ALL')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['order']['total'], 100)
        self.assertEqual(response.json()['payment']['amount'], 100)
        self.assert_reconciles()

    def test_use_is_counted_only_when_the_payment_succeeds(self):
        coupon = make_coupon(usage_limit=1)
        self.assert_error(self.buy_membership('SAVE10', test_outcome='failure'), 402, 'payment_failed')
        pending = self.buy_membership('SAVE10', test_outcome='pending')
        self.assertEqual(pending.status_code, 202)
        # The pending order shows the price it would be, but uses nothing.
        self.assertEqual(pending.json()['order']['total'], 45000)
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 0)
        self.assertEqual(CouponRedemption.objects.count(), 0)

        self.assertEqual(self.buy_membership('SAVE10').status_code, 201)
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 1)

    def test_per_user_limit(self):
        make_coupon(per_user_limit=1)
        self.assertEqual(self.buy_membership('SAVE10').status_code, 201)
        self.assert_error(self.buy_membership('SAVE10'), 400, 'coupon_invalid')
        # Someone else can still use it.
        self.login_as(self.make_user(email='ravi@example.com', college_id='SSA-002'))
        self.assertEqual(self.buy_membership('SAVE10').status_code, 201)
        self.assertEqual(Coupon.objects.get().used_count, 2)

    def test_usage_limit_across_users(self):
        make_coupon(usage_limit=1)
        self.assertEqual(self.buy_membership('SAVE10').status_code, 201)
        self.login_as(self.make_user(email='ravi@example.com', college_id='SSA-002'))
        response = self.buy_membership('SAVE10')
        self.assert_error(response, 400, 'coupon_invalid')
        self.assertIn('used up', response.json()['message'])
        self.assertEqual(Payment.objects.count(), 1)

    def test_a_replay_does_not_use_the_coupon_twice(self):
        coupon = make_coupon(per_user_limit=5)
        body = {'plan': self.plan.pk, 'coupon': 'SAVE10'}
        first = self.client.post('/api/memberships', body, format='json', HTTP_IDEMPOTENCY_KEY='same-key-0001')
        again = self.client.post('/api/memberships', body, format='json', HTTP_IDEMPOTENCY_KEY='same-key-0001')
        self.assertEqual((first.status_code, again.status_code), (201, 200))
        self.assertEqual(again.json()['order'], first.json()['order'])
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 1)

    def test_the_database_refuses_use_past_the_limit(self):
        coupon = make_coupon(usage_limit=1, used_count=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Coupon.objects.filter(pk=coupon.pk).update(used_count=2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_coupon('lower')            # codes are stored in upper case

    def test_trace_shows_the_coupon(self):
        make_coupon('WELCOME10', applies_to='membership')
        self.buy_membership('WELCOME10')
        self.login_as(self.make_role_user('treasurer'))
        entry = self.client.get('/api/finance/trace', {'figure': 'account:4000'}).json()['entries'][0]
        self.assertEqual(entry['amount'], 45000)
        details = entry['source']['details']
        self.assertEqual(
            (details['list_price'], details['discount'], details['coupon'], details['coupon_discount'], details['amount']),
            (50000, 5000, 'WELCOME10', 5000, 45000),
        )


@RAZORPAY_ON
class RazorpayWithCouponTests(CouponTestCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch('shop.razorpay.urlopen', FakeRazorpay())
        patcher.start()
        self.addCleanup(patcher.stop)

    def start(self, coupon='SAVE10'):
        return self.client.post(
            '/api/payments/razorpay/order', {'purpose': 'membership', 'plan': self.plan.pk, 'coupon': coupon},
            format='json', HTTP_IDEMPOTENCY_KEY=self.key(),
        )

    def verify(self, checkout, payment_id='pay_COUPON1'):
        return self.client.post('/api/payments/razorpay/verify', {
            'order_id': checkout['order_id'], 'razorpay_order_id': checkout['razorpay_order_id'],
            'razorpay_payment_id': payment_id,
            'razorpay_signature': sign(checkout['razorpay_order_id'], payment_id),
        }, format='json')

    def test_razorpay_charges_the_discounted_amount_and_counts_the_use_at_verify(self):
        coupon = make_coupon()
        checkout = self.start()
        self.assertEqual(checkout.status_code, 201, checkout.content)
        self.assertEqual(checkout.json()['amount'], 45000)
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 0)            # not paid yet

        response = self.verify(checkout.json())
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual((response.json()['order']['coupon'], response.json()['order']['total']), ('SAVE10', 45000))
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 1)
        self.assertEqual(self.verify(checkout.json()).status_code, 200)       # idempotent
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 1)
        self.assert_reconciles()

    def test_an_unusable_coupon_starts_no_checkout(self):
        self.assert_error(self.start('NOSUCH'), 400, 'coupon_invalid')
        self.assertEqual(Order.objects.count(), 0)

    def test_coupon_used_up_between_checkout_and_payment_is_flagged_for_refund(self):
        coupon = make_coupon(usage_limit=1)
        checkout = self.start().json()
        other = self.make_user(email='ravi@example.com', college_id='SSA-002')
        purchase_membership(user=other, plan=self.plan, outcome='success', idempotency_key='other-key-0001', coupon='SAVE10')

        self.assert_error(self.verify(checkout), 409, 'coupon_limit_reached')
        order = Order.objects.get(pk=checkout['order_id'])
        self.assertEqual((order.status, order.needs_refund, order.payment_ref), ('cancelled', True, 'pay_COUPON1'))
        self.assertEqual(Membership.objects.filter(user=self.user).count(), 0)
        self.assertEqual(Payment.objects.count(), 1)
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 1)
        # The same answer on a repeat.
        self.assert_error(self.verify(checkout), 409, 'coupon_limit_reached')
        self.assert_reconciles()


class CouponCrudTests(CouponTestCase):
    def setUp(self):
        super().setUp()
        self.treasurer = self.make_role_user('treasurer')
        self.login_as(self.treasurer)

    def body(self, **overrides):
        body = {'code': 'spring15', 'kind': 'percent', 'value': 15, 'applies_to': 'tickets'}
        body.update(overrides)
        return body

    def test_create_read_update_delete(self):
        response = self.client.post(COUPONS, self.body(), format='json')
        self.assertEqual(response.status_code, 201, response.content)
        created = response.json()
        self.assertEqual(set(created), {
            'id', 'code', 'kind', 'value', 'min_order', 'max_discount', 'valid_from', 'valid_to',
            'usage_limit', 'per_user_limit', 'applies_to', 'active', 'used_count', 'created_at',
        })
        self.assertEqual(
            (created['code'], created['min_order'], created['max_discount'], created['usage_limit'],
             created['per_user_limit'], created['active'], created['used_count']),
            ('SPRING15', 0, None, None, 1, True, 0),
        )
        url = f"{COUPONS}/{created['id']}"
        self.assertEqual(self.client.get(url).json()['code'], 'SPRING15')
        self.assertEqual(self.client.get(COUPONS).json()['count'], 1)

        patched = self.client.patch(url, {'active': False, 'usage_limit': 10}, format='json')
        self.assertEqual(patched.status_code, 200, patched.content)
        self.assertEqual((patched.json()['active'], patched.json()['usage_limit']), (False, 10))
        # used_count cannot be set through the API.
        self.client.patch(url, {'used_count': 9}, format='json')
        self.assertEqual(Coupon.objects.get().used_count, 0)

        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(Coupon.objects.count(), 0)
        self.assert_error(self.client.put(f'{COUPONS}/1', self.body(), format='json'), 405, 'method_not_allowed')

    def test_only_president_and_treasurer(self):
        coupon = make_coupon()
        for role in ['event_manager', 'volunteer_coordinator', 'member']:
            with self.subTest(role=role):
                self.login_as(self.make_role_user(role))
                self.assert_error(self.client.get(COUPONS), 403, 'permission_denied')
                self.assert_error(self.client.post(COUPONS, self.body(), format='json'), 403, 'permission_denied')
                self.assert_error(self.client.patch(f'{COUPONS}/{coupon.id}', {'active': False}, format='json'), 403, 'permission_denied')
                self.assert_error(self.client.delete(f'{COUPONS}/{coupon.id}'), 403, 'permission_denied')
        self.client.credentials()
        self.assert_error(self.client.get(COUPONS), 401, 'not_authenticated')
        self.login_as(self.make_role_user('president'))
        self.assertEqual(self.client.get(COUPONS).status_code, 200)
        coupon.refresh_from_db()
        self.assertTrue(coupon.active)
        self.assertEqual(Coupon.objects.count(), 1)

    def test_field_rules(self):
        make_coupon('TAKEN')
        now = timezone.now()
        cases = [
            ({'code': 'taken'}, 'code', 'unique'),
            ({'code': 'ab'}, 'code', 'invalid'),
            ({'code': 'has space'}, 'code', 'invalid'),
            ({'code': 'X' * 21}, 'code', 'invalid'),
            ({'kind': 'bogof'}, 'kind', 'invalid_choice'),
            ({'value': 0}, 'value', 'min_value'),
            ({'value': 101}, 'value', 'max_value'),
            ({'kind': 'flat', 'value': 1_000_000_001}, 'value', 'max_value'),
            ({'min_order': -1}, 'min_order', 'min_value'),
            ({'max_discount': 0}, 'max_discount', 'min_value'),
            ({'usage_limit': 0}, 'usage_limit', 'min_value'),
            ({'per_user_limit': 0}, 'per_user_limit', 'min_value'),
            ({'applies_to': 'everything'}, 'applies_to', 'invalid_choice'),
            ({'valid_from': now.isoformat(), 'valid_to': (now - timedelta(days=1)).isoformat()}, 'valid_to', 'ends_before_start'),
            ({'valid_from': 'tomorrow'}, 'valid_from', 'invalid'),
        ]
        for overrides, field, code in cases:
            with self.subTest(overrides=overrides):
                response = self.client.post(COUPONS, self.body(**overrides), format='json')
                body = self.assert_error(response, 400, 'validation_error', field)
                self.assertIn((field, code), self.field_codes(body))
        for missing in ['code', 'kind', 'value']:
            body = self.body()
            del body[missing]
            self.assert_error(self.client.post(COUPONS, body, format='json'), 400, 'validation_error', missing)
        self.assertEqual(Coupon.objects.count(), 1)
        # A flat coupon may be worth more than 100.
        self.assertEqual(self.client.post(COUPONS, self.body(kind='flat', value=5000), format='json').status_code, 201)

    def test_patch_rules_use_the_stored_values(self):
        coupon = make_coupon(used_count=3, usage_limit=5)
        url = f'{COUPONS}/{coupon.id}'
        body = self.assert_error(self.client.patch(url, {'usage_limit': 2}, format='json'), 400, 'validation_error', 'usage_limit')
        self.assertIn(('usage_limit', 'below_used_count'), self.field_codes(body))
        # Stored kind is percent, so 150 is too much even though kind was not sent.
        self.assert_error(self.client.patch(url, {'value': 150}, format='json'), 400, 'validation_error', 'value')
        self.assertEqual(self.client.patch(url, {'usage_limit': 3}, format='json').status_code, 200)

    def test_a_coupon_on_an_order_cannot_be_deleted(self):
        coupon = make_coupon()
        self.login_as(self.user)
        self.buy_membership('SAVE10')
        self.login_as(self.treasurer)
        self.assert_error(self.client.delete(f'{COUPONS}/{coupon.id}'), 409, 'coupon_in_use')
        self.assertTrue(Coupon.objects.filter(pk=coupon.pk).exists())


class ProductCatalogueTests(CouponTestCase):
    def setUp(self):
        super().setUp()
        self.staff = self.make_role_user('treasurer')

    def test_product_has_category_and_sale(self):
        self.login_as(self.staff)
        response = self.client.post('/api/products', {
            'name': 'Campus Mug', 'base_price': 30000, 'category': 'drinkware', 'sale_pct': 15, 'sized': False,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual((body['category'], body['sale_pct'], body['base_price'], body['price']),
                         ('drinkware', 15, 30000, 25500))
        # Not sized: one row, "ONE", holding the stock.
        self.assertEqual([size['size'] for size in body['sizes']], ['ONE'])
        restocked = self.client.post(f"/api/products/{body['id']}/restock", {'size': 'ONE', 'quantity': 4}, format='json')
        self.assertEqual(restocked.json()['sizes'][0]['stock'], 4)
        self.assert_error(
            self.client.post(f"/api/products/{body['id']}/restock", {'size': 'M', 'quantity': 4}, format='json'),
            404, 'not_found',
        )

    def test_defaults_are_apparel_no_sale_four_sizes(self):
        self.login_as(self.staff)
        body = self.client.post('/api/products', {'name': 'Scarf', 'base_price': 20000}, format='json').json()
        self.assertEqual((body['category'], body['sale_pct'], body['price']), ('apparel', 0, 20000))
        self.assertEqual([size['size'] for size in body['sizes']], ['S', 'M', 'L', 'XL'])

    def test_a_non_member_pays_the_sale_price_and_the_line_records_the_discount(self):
        product = make_product(base_price=30000, stock_by_size={'M': 3}, sale_pct=15)
        response = self.client.post(
            '/api/orders', {'items': [{'product_size': size_of(product, 'M').pk, 'quantity': 2}]},
            format='json', HTTP_IDEMPOTENCY_KEY=self.key(),
        )
        self.assertEqual(response.status_code, 201, response.content)
        order = response.json()['order']
        self.assertEqual((order['subtotal'], order['discount'], order['coupon_discount'], order['total']),
                         (60000, 9000, 0, 51000))
        self.assertEqual(account_balance('4200'), 51000)
        self.assert_reconciles()

    def test_the_database_refuses_a_sale_over_90(self):
        product = make_product()
        with self.assertRaises(IntegrityError), transaction.atomic():
            type(product).objects.filter(pk=product.pk).update(sale_pct=91)


class LastCouponUseRaceTests(TransactionTestCase):
    """A coupon with one use left and two buyers paying at the same instant.
    Threads, each with its own connection and committed transaction.
    """

    serialized_rollback = True

    def test_limit_one_two_buyers_one_wins(self):
        plan = MembershipPlan.objects.create(name='Basic', price=50000, duration_months=12)
        coupon = make_coupon('ONCE', usage_limit=1)
        buyers = [
            User.objects.create_user(email=f'buyer{n}@example.com', name=f'Buyer {n}', college_id=f'SSA-{n}')
            for n in range(2)
        ]
        barrier = threading.Barrier(2)
        outcomes = [None, None]

        def worker(index):
            try:
                barrier.wait(timeout=10)
                outcomes[index] = purchase_membership(
                    user=buyers[index], plan=plan, outcome='success',
                    idempotency_key=f'coupon-race-{index:04}', coupon='ONCE',
                )
            except Exception as exc:
                outcomes[index] = exc
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertFalse(any(thread.is_alive() for thread in threads), 'a purchase thread hung')

        refused = [outcome for outcome in outcomes if isinstance(outcome, Exception)]
        self.assertEqual([type(exc) for exc in refused], [coupons.CouponInvalid], outcomes)
        self.assertEqual(refused[0].reason, 'usage_limit_reached')
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 1)
        self.assertEqual(CouponRedemption.objects.count(), 1)
        # The loser bought nothing at all, at any price.
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Membership.objects.count(), 1)
        self.assertEqual(account_balance('4000'), 45000)
        self.assertTrue(reports.reconcile()['ok'])
