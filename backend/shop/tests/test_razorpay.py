import base64
import hashlib
import hmac
import json
import ssl
import threading
from unittest import mock
from urllib.error import HTTPError, URLError

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase, override_settings

from audit.models import AuditLog
from common.testing import ApiTestCase
from events.models import Ticket, TicketTier
from events.tests.helpers import make_event, make_member, make_tier
from finance import reports
from finance.models import LedgerEntry, LedgerLine
from finance.services import account_balance
from members.models import Membership, MembershipPlan
from shop import razorpay
from shop.models import Order, Payment, StockMovement
from shop.payments import IdempotencyConflict, purchase_membership, purchase_merch, tickets_basket
from shop.tests.helpers import make_product, size_of

User = get_user_model()

# Made up for the tests. Never real keys: every test replaces the HTTP call.
KEY_ID = 'rzp_test_FAKEKEYID'
KEY_SECRET = 'fake-secret-for-tests'
RAZORPAY_ON = override_settings(PAYMENT_GATEWAY='razorpay', RAZORPAY_KEY_ID=KEY_ID, RAZORPAY_KEY_SECRET=KEY_SECRET)

ORDER_URL = '/api/payments/razorpay/order'
VERIFY_URL = '/api/payments/razorpay/verify'
CANCEL_URL = '/api/payments/razorpay/cancel'


class FakeRazorpay:
    """Stands in for urlopen. Records each request and answers the way
    Razorpay's POST /v1/orders does.
    """

    def __init__(self):
        self.requests = []
        self.error = None

    def __call__(self, request, timeout=None, context=None):
        self.requests.append(request)
        self.timeout = timeout
        self.context = context
        if self.error:
            raise self.error
        sent = json.loads(request.data)
        reply = {'id': f'order_FAKE{len(self.requests):06}', 'amount': sent['amount'], 'currency': 'INR',
                 'receipt': sent['receipt'], 'status': 'created'}
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(reply).encode()
        return response


def sign(razorpay_order_id, payment_id, secret=KEY_SECRET):
    return hmac.new(secret.encode(), f'{razorpay_order_id}|{payment_id}'.encode(), hashlib.sha256).hexdigest()


class RazorpayTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.gateway = FakeRazorpay()
        patcher = mock.patch('shop.razorpay.urlopen', self.gateway)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.user = self.make_user()
        self.login_as(self.user)
        self.plan = MembershipPlan.objects.create(name='Basic', price=50000, duration_months=12)

    def start(self, body=None, key='razorpay-key-0001'):
        body = body or {'purpose': 'membership', 'plan': self.plan.pk}
        return self.client.post(ORDER_URL, body, format='json', HTTP_IDEMPOTENCY_KEY=key)

    def verify(self, checkout, payment_id='pay_FAKE000001', **overrides):
        body = {
            'order_id': checkout['order_id'],
            'razorpay_order_id': checkout['razorpay_order_id'],
            'razorpay_payment_id': payment_id,
            'razorpay_signature': sign(checkout['razorpay_order_id'], payment_id),
        }
        body.update(overrides)
        return self.client.post(VERIFY_URL, body, format='json')

    def assert_nothing_delivered(self):
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(Membership.objects.count(), 0)
        self.assertEqual(Ticket.objects.count(), 0)
        self.assertEqual(LedgerEntry.objects.count(), 0)
        self.assertEqual(StockMovement.objects.filter(reason='order').count(), 0)

    def assert_reconciles(self):
        result = reports.reconcile()
        self.assertTrue(result['ok'], [check for check in result['checks'] if not check['ok']])


class PaymentConfigTests(RazorpayTestCase):
    def test_needs_login(self):
        self.client.credentials()
        self.assert_error(self.client.get('/api/payments/config'), 401, 'not_authenticated')

    @override_settings(PAYMENT_GATEWAY='mock', RAZORPAY_KEY_ID=KEY_ID, RAZORPAY_KEY_SECRET=KEY_SECRET)
    def test_mock_gateway_reports_no_key(self):
        response = self.client.get('/api/payments/config')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'gateway': 'mock', 'key_id': None})

    @RAZORPAY_ON
    def test_razorpay_reports_the_key_id_and_never_the_secret(self):
        response = self.client.get('/api/payments/config')
        self.assertEqual(response.json(), {'gateway': 'razorpay', 'key_id': KEY_ID})
        self.assertNotIn(KEY_SECRET, response.content.decode())

    def test_razorpay_without_keys_falls_back_to_mock_and_warns(self):
        for key_id, secret in [('', KEY_SECRET), (KEY_ID, ''), ('', '')]:
            with self.subTest(key_id=key_id, secret=secret), override_settings(
                PAYMENT_GATEWAY='razorpay', RAZORPAY_KEY_ID=key_id, RAZORPAY_KEY_SECRET=secret,
            ):
                with self.assertLogs('shop.razorpay', level='WARNING') as logs:
                    response = self.client.get('/api/payments/config')
                    started = self.start()
                self.assertEqual(response.json(), {'gateway': 'mock', 'key_id': None})
                self.assertIn('using the mock gateway', logs.output[0])
                self.assert_error(started, 409, 'gateway_not_enabled')
                self.assertEqual(Order.objects.count(), 0)


@RAZORPAY_ON
class StartCheckoutTests(RazorpayTestCase):
    def test_membership_checkout(self):
        response = self.start()
        self.assertEqual(response.status_code, 201, response.content)
        order = Order.objects.get()
        self.assertEqual(response.json(), {
            'order_id': order.pk,
            'razorpay_order_id': 'order_FAKE000001',
            'key': KEY_ID,
            'amount': 50000,
            'currency': 'INR',
            'name': 'Skyline Student Association',
            'description': 'Basic membership',
            'prefill': {'name': 'Priya', 'email': 'priya@example.com'},
        })
        self.assertNotIn(KEY_SECRET, response.content.decode())
        self.assertEqual(order.status, 'pending')
        self.assertEqual(order.buyer, self.user)
        self.assertEqual(order.razorpay_order_id, 'order_FAKE000001')
        self.assertEqual(order.total, 50000)
        self.assert_nothing_delivered()

    def test_what_is_sent_to_razorpay(self):
        self.start()
        (request,) = self.gateway.requests
        order = Order.objects.get()
        self.assertEqual(request.full_url, 'https://api.razorpay.com/v1/orders')
        self.assertEqual(request.get_method(), 'POST')
        self.assertEqual(json.loads(request.data), {'amount': 50000, 'currency': 'INR', 'receipt': str(order.pk)})
        expected = 'Basic ' + base64.b64encode(f'{KEY_ID}:{KEY_SECRET}'.encode()).decode()
        self.assertEqual(request.get_header('Authorization'), expected)
        self.assertEqual(self.gateway.timeout, 10)
        # The certificate and the host name are always verified.
        self.assertEqual(self.gateway.context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(self.gateway.context.check_hostname)

    def test_needs_login_and_an_idempotency_key(self):
        self.assert_error(self.client.post(ORDER_URL, {'purpose': 'membership', 'plan': self.plan.pk}, format='json'),
                          400, 'idempotency_key_required')
        self.client.credentials()
        self.assert_error(self.start(), 401, 'not_authenticated')
        self.assertEqual(self.gateway.requests, [])

    def test_bad_bodies(self):
        for body, field in [
            ({'plan': self.plan.pk}, 'purpose'),
            ({'purpose': 'donation'}, 'purpose'),
            ({'purpose': 'membership'}, 'plan'),
            ({'purpose': 'membership', 'plan': 99999}, 'plan'),
            ({'purpose': 'tickets', 'quantity': 1}, 'tier'),
            ({'purpose': 'tickets', 'tier': 99999}, 'tier'),
            ({'purpose': 'merch'}, 'items'),
            ({'purpose': 'merch', 'items': []}, 'items'),
            # The old field name is not accepted in place of purpose.
            ({'kind': 'membership', 'plan': self.plan.pk}, 'purpose'),
        ]:
            with self.subTest(body=body):
                self.assert_error(self.start(body), 400, 'validation_error', field)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self.gateway.requests, [])

    def test_a_price_sent_by_the_client_is_ignored(self):
        response = self.start({'purpose': 'membership', 'plan': self.plan.pk, 'amount': 1, 'total': 1, 'price': 1})
        self.assertEqual(response.json()['amount'], 50000)
        self.assertEqual(json.loads(self.gateway.requests[0].data)['amount'], 50000)

    def test_ticket_checkout_uses_the_member_price_for_a_member(self):
        tier = make_tier(make_event())
        response = self.start({'purpose': 'tickets', 'event': tier.event_id, 'tier': tier.pk, 'quantity': 2})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['amount'], 160000)
        self.assertEqual(response.json()['description'], 'Spring Gala · General x2')

        make_member(self.user)
        response = self.start({'purpose': 'tickets', 'tier': tier.pk, 'quantity': 2}, key='razorpay-key-0002')
        self.assertEqual(response.json()['amount'], 120000)
        # A pending checkout holds no seat.
        tier.refresh_from_db()
        self.assertEqual(tier.sold_count, 0)

    def test_ticket_checkout_is_validated_like_the_mock_purchase(self):
        event = make_event()
        tier = make_tier(event, capacity=1)
        other_event = make_event(title='Other')
        draft_tier = make_tier(make_event(title='Draft', status='draft'))

        self.assert_error(self.start({'purpose': 'tickets', 'tier': tier.pk, 'quantity': 2}), 409, 'sold_out')
        self.assert_error(
            self.start({'purpose': 'tickets', 'event': other_event.pk, 'tier': tier.pk}), 400, 'validation_error', 'tier',
        )
        self.assert_error(self.start({'purpose': 'tickets', 'tier': draft_tier.pk}), 400, 'validation_error', 'tier')
        event.status = 'closed'
        event.save()
        self.assert_error(self.start({'purpose': 'tickets', 'tier': tier.pk}), 409, 'sales_closed')
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self.gateway.requests, [])

    def test_merch_checkout_applies_the_member_discount_and_checks_stock(self):
        product = make_product(stock_by_size={'M': 2})
        size = size_of(product, 'M')
        self.plan.merch_discount_pct = 10
        self.plan.save()
        Membership.objects.all().delete()
        make_member(self.user)

        self.assert_error(
            self.start({'purpose': 'merch', 'items': [{'product_size': size.pk, 'quantity': 3}]}), 409, 'out_of_stock',
        )
        self.assert_error(
            self.start({'purpose': 'merch', 'items': [{'product_size': 99999, 'quantity': 1}]}), 409, 'product_unavailable',
        )
        self.assertEqual(Order.objects.count(), 0)

        response = self.start({'purpose': 'merch', 'items': [{'product_size': size.pk, 'quantity': 2}]})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['amount'], 216000)  # 2 x 1200.00 less 10%
        self.assertEqual(response.json()['description'], 'Hoodie · M x2')
        order = Order.objects.get()
        self.assertEqual((order.subtotal, order.discount, order.total), (240000, 24000, 216000))
        size.refresh_from_db()
        self.assertEqual(size.stock, 2)

    def test_same_key_and_purchase_returns_the_same_checkout_without_a_second_gateway_call(self):
        first = self.start()
        again = self.start()
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json(), first.json())
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(len(self.gateway.requests), 1)

    def test_key_reuse_is_refused(self):
        other_plan = MembershipPlan.objects.create(name='Plus', price=90000, duration_months=12)
        checkout = self.start().json()

        self.assert_error(self.start({'purpose': 'membership', 'plan': other_plan.pk}), 409, 'idempotency_key_reused')
        # The mock gateway refuses the key too: it is reserved for the
        # payment this checkout will create. (Called as a service: the mock
        # endpoints themselves are closed while Razorpay is on.)
        with self.assertRaises(IdempotencyConflict):
            purchase_membership(
                user=self.user, plan=self.plan, outcome='success', idempotency_key='razorpay-key-0001',
            )

        self.login_as(self.make_user(email='arjun@example.com', college_id='SSA-002'))
        self.assert_error(self.start(), 409, 'idempotency_key_reused')

        self.login_as(self.user)
        self.assertEqual(self.verify(checkout).status_code, 201)
        self.assert_error(self.start(), 409, 'idempotency_key_reused')
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Payment.objects.count(), 1)

    def test_a_key_already_used_by_a_mock_purchase_is_refused(self):
        purchase_membership(user=self.user, plan=self.plan, outcome='success', idempotency_key='razorpay-key-0001')
        self.assert_error(self.start(), 409, 'idempotency_key_reused')
        self.assertEqual(self.gateway.requests, [])

    def test_gateway_down_gives_502_and_leaves_no_open_order(self):
        errors = [
            URLError('connection refused'),
            TimeoutError('timed out'),
            HTTPError(razorpay.ORDERS_URL, 401, 'Unauthorized', {}, None),
            HTTPError(razorpay.ORDERS_URL, 500, 'Server Error', {}, None),
        ]
        for error in errors:
            with self.subTest(error=error):
                self.gateway.error = error
                with self.assertLogs('shop.razorpay', level='ERROR') as logs:
                    response = self.start()
                self.assert_error(response, 502, 'gateway_unavailable')
                self.assertNotIn(KEY_SECRET, response.content.decode() + ''.join(logs.output))
        self.assertEqual(set(Order.objects.values_list('status', 'razorpay_order_id')), {('cancelled', '')})
        self.assert_nothing_delivered()

        # The same key works once the gateway is back.
        self.gateway.error = None
        response = self.start()
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(Order.objects.filter(status='pending').count(), 1)

    def test_an_unexpected_reply_from_the_gateway_is_a_502(self):
        for reply in [b'<html>', b'{}', b'{"id": "order_X", "amount": 1}', b'[]']:
            with self.subTest(reply=reply):
                response = mock.MagicMock()
                response.__enter__.return_value.read.return_value = reply
                with mock.patch('shop.razorpay.urlopen', return_value=response), self.assertLogs('shop.razorpay'):
                    self.assert_error(self.start(), 502, 'gateway_unavailable')
        self.assertFalse(Order.objects.filter(status='pending').exists())

    def test_total_under_one_rupee_is_refused(self):
        tier = make_tier(make_event(), public_price=50, member_price=50)
        self.assert_error(self.start({'purpose': 'tickets', 'tier': tier.pk}), 400, 'amount_too_small')
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self.gateway.requests, [])


@RAZORPAY_ON
class VerifyTests(RazorpayTestCase):
    def test_valid_signature_pays_the_membership(self):
        checkout = self.start().json()
        response = self.verify(checkout)
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        # The same shape as POST /memberships.
        self.assertEqual(set(body), {'order', 'payment', 'membership'})
        order = Order.objects.get()
        payment = Payment.objects.get()
        membership = Membership.objects.get()
        self.assertEqual(body['order']['id'], order.pk)
        self.assertEqual(body['order']['status'], 'paid')
        self.assertEqual(body['order']['payment_ref'], 'pay_FAKE000001')
        self.assertIs(body['order']['needs_refund'], False)
        self.assertEqual(body['payment']['gateway_ref'], 'pay_FAKE000001')
        self.assertEqual(body['payment']['amount'], 50000)
        self.assertEqual(body['membership']['id'], membership.pk)
        self.assertEqual(body['membership']['status'], 'active')

        self.assertEqual((payment.order, payment.amount, payment.gateway_ref), (order, 50000, 'pay_FAKE000001'))
        self.assertEqual(membership.user, self.user)
        entry = LedgerEntry.objects.get()
        self.assertEqual((entry.kind, entry.source_type, entry.source_id), ('membership_dues', 'payment', payment.pk))
        self.assertEqual(
            sorted(LedgerLine.objects.values_list('account__code', 'debit', 'credit')),
            [('1000', 50000, 0), ('4000', 0, 50000)],
        )
        self.assert_reconciles()

    def test_valid_signature_pays_for_tickets(self):
        tier = make_tier(make_event())
        checkout = self.start({'purpose': 'tickets', 'tier': tier.pk, 'quantity': 2}).json()
        response = self.verify(checkout)
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        # The same shape as POST /events/{id}/tickets.
        self.assertEqual(set(body), {'order', 'payment', 'tickets', 'pass'})
        self.assertEqual(len(body['tickets']), 2)
        self.assertEqual((body['pass']['quantity'], body['pass']['remaining']), (2, 2))
        self.assertEqual(Ticket.objects.filter(owner=self.user, price_paid=80000).count(), 2)
        tier.refresh_from_db()
        self.assertEqual(tier.sold_count, 2)
        self.assertEqual(account_balance('4100'), 160000)
        self.assertEqual(account_balance('1000'), 160000)
        self.assert_reconciles()

    def test_valid_signature_pays_for_merch(self):
        product = make_product(stock_by_size={'M': 3, 'L': 1})
        items = [{'product_size': size_of(product, 'L').pk, 'quantity': 1},
                 {'product_size': size_of(product, 'M').pk, 'quantity': 2}]
        checkout = self.start({'purpose': 'merch', 'items': items}).json()
        response = self.verify(checkout)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(set(response.json()), {'order', 'payment'})
        self.assertEqual(size_of(product, 'M').stock, 1)
        self.assertEqual(size_of(product, 'L').stock, 0)
        self.assertEqual(StockMovement.objects.filter(reason='order').count(), 2)
        self.assertEqual(LedgerEntry.objects.get().kind, 'merch_sale')
        self.assertEqual(account_balance('4200'), 360000)
        self.assert_reconciles()

    def test_bad_signature_is_a_400_and_nothing_is_created(self):
        checkout = self.start().json()
        real = sign(checkout['razorpay_order_id'], 'pay_FAKE000001')
        attempts = [
            {'razorpay_signature': 'not-a-signature'},
            {'razorpay_signature': real[:-1] + ('0' if real[-1] != '0' else '1')},
            {'razorpay_signature': real.upper()},
            {'razorpay_signature': 'ü' * 64},
            # Signed with a different secret.
            {'razorpay_signature': sign(checkout['razorpay_order_id'], 'pay_FAKE000001', secret='guess')},
            # A genuine signature, but for another payment id.
            {'razorpay_signature': sign(checkout['razorpay_order_id'], 'pay_OTHER')},
            # A correctly signed pair that is not this order's Razorpay order.
            {'razorpay_order_id': 'order_OTHER', 'razorpay_signature': sign('order_OTHER', 'pay_FAKE000001')},
        ]
        for overrides in attempts:
            with self.subTest(overrides=overrides):
                self.assert_error(self.verify(checkout, **overrides), 400, 'invalid_signature')
        self.assertEqual(Order.objects.get().status, 'pending')
        self.assertEqual(Order.objects.get().payment_ref, '')
        self.assert_nothing_delivered()

        # The order is still payable with the real signature.
        self.assertEqual(self.verify(checkout).status_code, 201)

    def test_missing_fields_are_validation_errors(self):
        checkout = self.start().json()
        for field in ['order_id', 'razorpay_order_id', 'razorpay_payment_id', 'razorpay_signature']:
            with self.subTest(field=field):
                body = {'order_id': checkout['order_id'], 'razorpay_order_id': checkout['razorpay_order_id'],
                        'razorpay_payment_id': 'pay_X', 'razorpay_signature': 'x'}
                del body[field]
                self.assert_error(self.client.post(VERIFY_URL, body, format='json'), 400, 'validation_error', field)
        self.assert_nothing_delivered()

    def test_verifying_twice_returns_the_same_result_and_creates_nothing_more(self):
        tier = make_tier(make_event())
        checkout = self.start({'purpose': 'tickets', 'tier': tier.pk, 'quantity': 2}).json()
        first = self.verify(checkout)
        second = self.verify(checkout)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json(), first.json())
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Ticket.objects.count(), 2)
        self.assertEqual(LedgerEntry.objects.count(), 1)
        tier.refresh_from_db()
        self.assertEqual(tier.sold_count, 2)
        self.assertEqual(account_balance('1000'), 160000)
        self.assert_reconciles()

    def test_a_second_payment_for_a_paid_order_is_refused(self):
        checkout = self.start().json()
        self.verify(checkout)
        self.assert_error(self.verify(checkout, payment_id='pay_FAKE000002'), 409, 'order_already_paid')
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Membership.objects.count(), 1)

    def test_seats_gone_by_verify_time_is_a_409_flagged_for_refund(self):
        tier = make_tier(make_event(), capacity=1)
        checkout = self.start({'purpose': 'tickets', 'tier': tier.pk}).json()
        TicketTier.objects.filter(pk=tier.pk).update(sold_count=1)  # someone else took the seat

        response = self.verify(checkout)
        self.assert_error(response, 409, 'sold_out')
        order = Order.objects.get()
        self.assertEqual((order.status, order.needs_refund, order.payment_ref), ('cancelled', True, 'pay_FAKE000001'))
        self.assert_nothing_delivered()
        tier.refresh_from_db()
        self.assertEqual(tier.sold_count, 1)

        log = AuditLog.objects.get(action='order.refund_due')
        self.assertEqual((log.actor, log.object_type, log.object_id), (self.user, 'shop.order', order.pk))
        self.assertEqual(log.before, {'status': 'pending', 'needs_refund': False})
        self.assertEqual(log.after, {
            'status': 'cancelled', 'needs_refund': True, 'reason': 'sold_out', 'amount': 80000,
            'razorpay_order_id': checkout['razorpay_order_id'], 'razorpay_payment_id': 'pay_FAKE000001',
        })

        # Asking again gives the same answer and no second audit row.
        self.assert_error(self.verify(checkout), 409, 'sold_out')
        self.assertEqual(AuditLog.objects.filter(action='order.refund_due').count(), 1)
        self.assertTrue(self.client.get('/api/orders/me').json()['results'][0]['needs_refund'])

    def test_stock_gone_by_verify_time_is_a_409_and_no_line_is_delivered(self):
        product = make_product(stock_by_size={'M': 2, 'L': 1})
        medium, large = size_of(product, 'M'), size_of(product, 'L')
        items = [{'product_size': medium.pk, 'quantity': 2}, {'product_size': large.pk, 'quantity': 1}]
        checkout = self.start({'purpose': 'merch', 'items': items}).json()
        # The last L is sold to someone else meanwhile.
        other = self.make_user(email='arjun@example.com', college_id='SSA-002')
        purchase_merch(user=other, items={large.pk: 1}, outcome='success', idempotency_key='mock-key-0001')

        self.assert_error(self.verify(checkout), 409, 'sold_out')
        order = Order.objects.get(pk=checkout['order_id'])
        self.assertEqual((order.status, order.needs_refund), ('cancelled', True))
        # M was in stock, but the order is all or nothing: it was not taken.
        medium.refresh_from_db()
        self.assertEqual(medium.stock, 2)
        self.assertEqual(Payment.objects.count(), 1)  # only the other buyer's
        self.assertEqual(account_balance('4200'), 120000)
        self.assertEqual(AuditLog.objects.filter(action='order.refund_due').count(), 1)
        self.assert_reconciles()

    def test_another_user_cannot_verify_or_cancel_and_gets_a_404(self):
        checkout = self.start().json()
        self.login_as(self.make_user(email='arjun@example.com', college_id='SSA-002'))
        self.assert_error(self.verify(checkout), 404, 'not_found')
        self.assert_error(self.client.post(CANCEL_URL, {'order_id': checkout['order_id']}, format='json'), 404, 'not_found')
        self.assert_error(self.verify({**checkout, 'order_id': 99999}), 404, 'not_found')
        self.assertEqual(Order.objects.get().status, 'pending')
        self.assert_nothing_delivered()

        self.client.credentials()
        self.assert_error(self.verify(checkout), 401, 'not_authenticated')

    def test_an_order_from_the_mock_gateway_cannot_be_verified_or_cancelled(self):
        order_id = purchase_membership(
            user=self.user, plan=self.plan, outcome='pending', idempotency_key='mock-key-0001',
        ).order.pk
        fake = {'order_id': order_id, 'razorpay_order_id': ''}
        body = {'order_id': order_id, 'razorpay_order_id': 'order_X', 'razorpay_payment_id': 'pay_X',
                'razorpay_signature': sign('order_X', 'pay_X')}
        self.assert_error(self.client.post(VERIFY_URL, body, format='json'), 404, 'not_found')
        self.assert_error(self.client.post(CANCEL_URL, fake, format='json'), 404, 'not_found')
        self.assertEqual(Order.objects.get().status, 'pending')
        self.assert_nothing_delivered()


@RAZORPAY_ON
class CancelTests(RazorpayTestCase):
    def cancel(self, checkout):
        return self.client.post(CANCEL_URL, {'order_id': checkout['order_id']}, format='json')

    def test_cancel_closes_the_pending_order(self):
        checkout = self.start().json()
        response = self.cancel(checkout)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(set(response.json()), {'order'})
        self.assertEqual(response.json()['order']['id'], checkout['order_id'])
        self.assertEqual(response.json()['order']['status'], 'cancelled')
        self.assertIs(response.json()['order']['needs_refund'], False)
        self.assertEqual(Order.objects.get().status, 'cancelled')
        # Again: same answer.
        self.assertEqual(self.cancel(checkout).json(), response.json())
        self.assert_nothing_delivered()
        # The key belongs to the closed checkout; a new attempt needs a new one.
        self.assert_error(self.start(), 409, 'idempotency_key_reused')
        self.assertEqual(self.start(key='razorpay-key-0002').status_code, 201)

    def test_a_paid_order_cannot_be_cancelled(self):
        checkout = self.start().json()
        self.verify(checkout)
        self.assert_error(self.cancel(checkout), 409, 'order_already_paid')
        self.assertEqual(Order.objects.get().status, 'paid')
        self.assertEqual(Membership.objects.count(), 1)

    def test_a_genuine_payment_that_arrives_after_cancel_is_still_delivered(self):
        checkout = self.start().json()
        self.cancel(checkout)
        self.assert_error(self.verify(checkout, razorpay_signature='wrong'), 400, 'invalid_signature')
        self.assertEqual(Order.objects.get().status, 'cancelled')

        response = self.verify(checkout)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(Order.objects.get().status, 'paid')
        self.assertEqual(Membership.objects.count(), 1)
        self.assert_reconciles()


class MockGatewayStillWorksTests(RazorpayTestCase):
    def buy_with_mock(self):
        return self.client.post(
            '/api/memberships', {'plan': self.plan.pk}, format='json', HTTP_IDEMPOTENCY_KEY='mock-key-0001',
        )

    @override_settings(PAYMENT_GATEWAY='mock', RAZORPAY_KEY_ID='', RAZORPAY_KEY_SECRET='')
    def test_mock_purchase_works_and_razorpay_endpoints_are_off(self):
        response = self.buy_with_mock()
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body['order']['status'], 'paid')
        self.assertTrue(body['payment']['gateway_ref'].startswith('mock_'))
        self.assertIs(body['order']['needs_refund'], False)
        order = Order.objects.get()
        self.assertEqual((order.razorpay_order_id, order.idempotency_key), ('', ''))
        self.assertEqual(self.buy_with_mock().status_code, 200)
        self.assertEqual(Payment.objects.count(), 1)
        self.assert_reconciles()

        self.assert_error(self.start(), 409, 'gateway_not_enabled')
        verify = {'order_id': order.pk, 'razorpay_order_id': 'order_X', 'razorpay_payment_id': 'pay_X',
                  'razorpay_signature': 'x'}
        self.assert_error(self.client.post(VERIFY_URL, verify, format='json'), 409, 'gateway_not_enabled')
        self.assert_error(self.client.post(CANCEL_URL, {'order_id': order.pk}, format='json'), 409, 'gateway_not_enabled')
        self.assertEqual(self.gateway.requests, [])

    @RAZORPAY_ON
    def test_mock_endpoints_are_closed_while_razorpay_is_on(self):
        tier = make_tier(make_event())
        size = size_of(make_product(stock_by_size={'M': 2}), 'M')
        attempts = [
            ('/api/memberships', {'plan': self.plan.pk}),
            (f'/api/events/{tier.event_id}/tickets', {'tier': tier.pk}),
            ('/api/orders', {'items': [{'product_size': size.pk, 'quantity': 1}]}),
        ]
        for outcome in ['success', 'failure', 'pending']:
            for number, (url, body) in enumerate(attempts):
                with self.subTest(url=url, outcome=outcome):
                    response = self.client.post(
                        url, {**body, 'test_outcome': outcome}, format='json',
                        HTTP_IDEMPOTENCY_KEY=f'closed-{outcome}-{number}',
                    )
                    self.assert_error(response, 409, 'gateway_not_enabled')
        # Refused before anything else is looked at, even the key.
        self.assert_error(self.client.post('/api/memberships', {}, format='json'), 409, 'gateway_not_enabled')
        self.assertEqual(Order.objects.count(), 0)
        self.assert_nothing_delivered()
        size.refresh_from_db()
        tier.refresh_from_db()
        self.assertEqual((size.stock, tier.sold_count), (2, 0))
        # Reading is unaffected, and so is the Razorpay flow.
        self.assertEqual(self.client.get('/api/plans').status_code, 200)
        self.assertEqual(self.start().status_code, 201)

    def test_razorpay_without_keys_leaves_the_mock_endpoints_open(self):
        with override_settings(PAYMENT_GATEWAY='razorpay', RAZORPAY_KEY_ID='', RAZORPAY_KEY_SECRET=''):
            with self.assertLogs('shop.razorpay', level='WARNING'):
                self.assertEqual(self.buy_with_mock().status_code, 201)

    @RAZORPAY_ON
    def test_mock_and_razorpay_purchases_reconcile_together(self):
        purchase_membership(user=self.user, plan=self.plan, outcome='success', idempotency_key='mock-key-0001')
        self.assertEqual(self.verify(self.start().json()).status_code, 201)
        self.assertEqual(Payment.objects.count(), 2)
        self.assertEqual(account_balance('1000'), 100000)
        self.assert_reconciles()


@RAZORPAY_ON
class LastSeatAtVerifyRaceTests(TransactionTestCase):
    """Two buyers have both paid Razorpay for the last seat and verify at
    the same instant. Exactly one gets the ticket; the other is flagged for
    a refund. Threads, each with its own connection and committed
    transaction.
    """

    serialized_rollback = True

    def test_one_ticket_one_refund(self):
        tier = make_tier(make_event(), capacity=1)
        users = [
            User.objects.create_user(email=f'buyer{n}@example.com', name=f'Buyer {n}', college_id=f'SSA-{n}')
            for n in range(2)
        ]
        with mock.patch('shop.razorpay.urlopen', FakeRazorpay()):
            orders = [
                razorpay.start_checkout(
                    user=user, idempotency_key=f'seat-race-{n:04}',
                    **tickets_basket(user=user, tier_id=tier.pk, quantity=1),
                )[0]
                for n, user in enumerate(users)
            ]
        barrier = threading.Barrier(2)
        outcomes = [None, None]

        def worker(index):
            order = orders[index]
            try:
                barrier.wait(timeout=10)
                outcomes[index] = razorpay.verify_payment(
                    user=users[index], order_id=order.pk, razorpay_order_id=order.razorpay_order_id,
                    razorpay_payment_id=f'pay_RACE{index}',
                    signature=sign(order.razorpay_order_id, f'pay_RACE{index}'),
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
        self.assertFalse(any(thread.is_alive() for thread in threads), 'a verify thread hung')

        refused = [outcome for outcome in outcomes if isinstance(outcome, Exception)]
        self.assertEqual([type(exc) for exc in refused], [razorpay.SoldOutAfterPayment], outcomes)
        tier.refresh_from_db()
        self.assertEqual(tier.sold_count, 1)
        self.assertEqual(Ticket.objects.count(), 1)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(sorted(Order.objects.values_list('status', 'needs_refund')), [('cancelled', True), ('paid', False)])
        self.assertEqual(AuditLog.objects.filter(action='order.refund_due').count(), 1)
        self.assertEqual(account_balance('4100'), 80000)
        self.assertTrue(reports.reconcile()['ok'])
