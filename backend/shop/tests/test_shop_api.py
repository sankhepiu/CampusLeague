from django.db import IntegrityError, transaction

from audit.models import AuditLog
from common.testing import ApiTestCase
from events.tests.helpers import make_member
from finance.models import LedgerEntry
from finance.services import account_balance
from members.models import MembershipPlan
from shop import stock
from shop.models import Order, OrderLine, Payment, Product, ProductSize, StockMovement
from shop.tests.helpers import make_product, size_of

PRODUCTS = '/api/products'
ORDERS = '/api/orders'
KEY = 'merch-key-0001'
OTHER_KEY = 'merch-key-0002'


class ShopTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.hoodie = make_product('Hoodie', 120000, {'S': 3, 'M': 5, 'L': 2, 'XL': 1})
        self.medium = size_of(self.hoodie, 'M')
        self.user = self.make_user()
        self.login_as(self.user)

    def order(self, items=None, key=KEY, **body):
        if items is None:
            items = [{'product_size': self.medium.id, 'quantity': 1}]
        return self.client.post(
            ORDERS, {'items': items, **body}, format='json', headers={'Idempotency-Key': key},
        )

    def stock_of(self, size):
        size.refresh_from_db()
        return size.stock

    def assert_nothing_sold(self, orders=0):
        self.assertEqual(self.stock_of(self.medium), 5)
        self.assertEqual(StockMovement.objects.filter(reason='order').count(), 0)
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(LedgerEntry.objects.count(), 0)
        self.assertEqual(Order.objects.count(), orders)
        self.assertEqual(stock.stock_mismatches(), [])


class ProductListTests(ShopTestCase):
    def test_public_list_shows_per_size_stock_in_size_order(self):
        self.client.credentials()
        body = self.client.get(PRODUCTS).json()

        self.assertEqual(body['count'], 1)
        product = body['results'][0]
        self.assertEqual((product['name'], product['base_price'], product['price']), ('Hoodie', 120000, 120000))
        self.assertEqual([(s['size'], s['stock']) for s in product['sizes']], [('S', 3), ('M', 5), ('L', 2), ('XL', 1)])

    def test_price_reflects_the_callers_merch_discount(self):
        self.assertEqual(self.client.get(PRODUCTS).json()['results'][0]['price'], 120000)
        membership = make_member(self.user)
        MembershipPlan.objects.filter(pk=membership.plan_id).update(merch_discount_pct=10)
        self.assertEqual(self.client.get(PRODUCTS).json()['results'][0]['price'], 108000)

    def test_inactive_products_are_hidden_from_shoppers_but_not_staff(self):
        make_product('Old Cap', 30000, active=False)
        self.assertEqual(self.client.get(PRODUCTS).json()['count'], 1)
        self.login_as(self.make_role_user('treasurer'))
        self.assertEqual(self.client.get(PRODUCTS).json()['count'], 2)


class MerchOrderTests(ShopTestCase):
    def test_buying_size_m_lowers_its_stock_by_one(self):
        response = self.order()

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body['order']['status'], 'paid')
        self.assertEqual((body['order']['subtotal'], body['order']['discount'], body['order']['total']), (120000, 0, 120000))
        self.assertEqual(body['payment']['amount'], 120000)
        self.assertEqual(self.stock_of(self.medium), 4)
        movement = StockMovement.objects.get(reason='order')
        self.assertEqual((movement.product_size, movement.delta, movement.order_line), (self.medium, -1, OrderLine.objects.get()))
        self.assertEqual(self.stock_of(size_of(self.hoodie, 'S')), 3)   # other sizes untouched

    def test_one_ledger_entry_per_order_to_merchandise_revenue(self):
        tee = make_product('T-Shirt', 40000, {'L': 10})
        self.order(items=[
            {'product_size': self.medium.id, 'quantity': 2},
            {'product_size': size_of(tee, 'L').id, 'quantity': 3},
        ])

        entry, order = LedgerEntry.objects.get(), Order.objects.get()
        self.assertEqual((entry.source_type, entry.source_id, entry.kind), ('order', order.id, 'merch_sale'))
        self.assertEqual(
            sorted(entry.lines.values_list('account__code', 'debit', 'credit')),
            [('1000', 360000, 0), ('4200', 0, 360000)],
        )
        self.assertEqual(OrderLine.objects.count(), 2)
        self.assertEqual(StockMovement.objects.filter(reason='order').count(), 2)
        self.assertEqual(self.stock_of(self.medium), 3)
        self.assertEqual(self.stock_of(size_of(tee, 'L')), 7)

    def test_active_member_gets_the_plan_discount_and_revenue_is_what_was_paid(self):
        membership = make_member(self.user)
        MembershipPlan.objects.filter(pk=membership.plan_id).update(merch_discount_pct=10)

        body = self.order(items=[{'product_size': self.medium.id, 'quantity': 2}]).json()

        self.assertEqual((body['order']['subtotal'], body['order']['discount'], body['order']['total']), (240000, 24000, 216000))
        line = body['order']['lines'][0]
        self.assertEqual((line['unit_price'], line['discount'], line['qty']), (120000, 24000, 2))
        self.assertEqual(Payment.objects.get().amount, 216000)
        self.assertEqual(account_balance('4200'), 216000)

    def test_lapsed_member_gets_no_discount(self):
        membership = make_member(self.user, days_left=-1)
        MembershipPlan.objects.filter(pk=membership.plan_id).update(merch_discount_pct=10)
        self.assertEqual(self.order().json()['order']['total'], 120000)

    def test_discount_is_rounded_down_to_whole_paise(self):
        odd = make_product('Sticker', 999, {'S': 5})
        membership = make_member(self.user)
        MembershipPlan.objects.filter(pk=membership.plan_id).update(merch_discount_pct=15)
        body = self.order(items=[{'product_size': size_of(odd, 'S').id, 'quantity': 1}]).json()
        self.assertEqual((body['order']['discount'], body['order']['total']), (149, 850))   # 149.85 -> 149

    def test_price_and_discount_sent_by_the_client_are_ignored(self):
        response = self.order(
            items=[{'product_size': self.medium.id, 'quantity': 1, 'unit_price': 1, 'price': 1, 'discount': 119999}],
            total=1, discount=119999, merch_discount_pct=100, buyer=999,
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(Payment.objects.get().amount, 120000)
        self.assertEqual(Order.objects.get().buyer, self.user)
        self.assertEqual(account_balance('4200'), 120000)

    def test_replay_returns_the_first_order_and_takes_no_more_stock(self):
        first = self.order()
        replay = self.order()

        self.assertEqual(replay.status_code, 200, replay.content)
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(self.stock_of(self.medium), 4)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(account_balance('1000'), 120000)

    def test_same_key_for_a_different_basket_is_a_conflict(self):
        self.order()
        response = self.order(items=[{'product_size': self.medium.id, 'quantity': 2}])
        self.assert_error(response, 409, 'idempotency_key_reused')
        self.assertEqual(self.stock_of(self.medium), 4)

    def test_failed_payment_leaves_stock_alone(self):
        self.assert_error(self.order(test_outcome='failure'), 402, 'payment_failed')
        self.assert_nothing_sold(orders=1)
        self.assertEqual(Order.objects.get().status, 'cancelled')

    def test_pending_payment_leaves_stock_alone(self):
        self.assertEqual(self.order(test_outcome='pending').status_code, 202)
        self.assert_nothing_sold(orders=1)

    def test_my_orders_lists_only_mine(self):
        self.order()
        other = self.make_user(email='ravi@example.com', name='Ravi', college_id='SSA-002')
        self.login_as(other)
        self.order(key=OTHER_KEY, items=[{'product_size': self.medium.id, 'quantity': 2}])

        mine = self.client.get('/api/orders/me').json()

        self.assertEqual(mine['count'], 1)
        self.assertEqual(mine['results'][0]['total'], 240000)
        self.client.credentials()
        self.assert_error(self.client.get('/api/orders/me'), 401, 'not_authenticated')


class StockLimitTests(ShopTestCase):
    """R14: "atomic decrement; blocked at zero"."""

    def test_last_item_can_be_bought_then_the_size_is_blocked(self):
        xl = size_of(self.hoodie, 'XL')   # stock 1
        self.assertEqual(self.order(items=[{'product_size': xl.id, 'quantity': 1}]).status_code, 201)
        self.assertEqual(self.stock_of(xl), 0)

        response = self.order(items=[{'product_size': xl.id, 'quantity': 1}], key=OTHER_KEY)

        body = self.assert_error(response, 409, 'out_of_stock')
        self.assertIn('Hoodie size XL', body['message'])
        self.assertEqual(self.stock_of(xl), 0)
        self.assertEqual(Order.objects.count(), 1)     # nothing created for the refused buyer

    def test_asking_for_more_than_is_left_takes_none(self):
        large = size_of(self.hoodie, 'L')   # stock 2
        self.assert_error(self.order(items=[{'product_size': large.id, 'quantity': 3}]), 409, 'out_of_stock')
        self.assertEqual(self.stock_of(large), 2)
        self.assert_nothing_sold()

    def test_one_unavailable_line_refuses_the_whole_basket(self):
        xl = size_of(self.hoodie, 'XL')
        response = self.order(items=[
            {'product_size': self.medium.id, 'quantity': 1}, {'product_size': xl.id, 'quantity': 2},
        ])
        self.assert_error(response, 409, 'out_of_stock')
        self.assertEqual(self.stock_of(xl), 1)
        self.assert_nothing_sold()

    def test_database_refuses_negative_stock(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProductSize.objects.filter(pk=self.medium.pk).update(stock=-1)
        self.assertEqual(self.stock_of(self.medium), 5)

    def test_stock_always_equals_the_sum_of_its_movements(self):
        self.order(items=[{'product_size': self.medium.id, 'quantity': 2}])
        self.order(key=OTHER_KEY, items=[{'product_size': size_of(self.hoodie, 'S').id, 'quantity': 1}])
        self.order(key='merch-key-0003', test_outcome='failure')
        self.assertEqual(stock.stock_mismatches(), [])
        for size in ProductSize.objects.all():
            self.assertEqual(size.stock, sum(size.movements.values_list('delta', flat=True)), size)

    def test_mismatch_check_detects_stock_edited_without_a_movement(self):
        ProductSize.objects.filter(pk=self.medium.pk).update(stock=50)
        self.assertEqual(stock.stock_mismatches(), [self.medium])

    def test_inactive_product_cannot_be_bought(self):
        Product.objects.filter(pk=self.hoodie.pk).update(active=False)
        self.assert_error(self.order(), 409, 'product_unavailable')
        self.assert_nothing_sold()

    def test_unknown_size_id_cannot_be_bought(self):
        self.assert_error(self.order(items=[{'product_size': 999999, 'quantity': 1}]), 409, 'product_unavailable')
        self.assert_nothing_sold()

    def test_invalid_baskets_are_refused(self):
        m = self.medium.id
        bad = [
            [], [{'product_size': m, 'quantity': 0}], [{'product_size': m, 'quantity': -1}],
            [{'product_size': m, 'quantity': 11}], [{'product_size': m, 'quantity': 'two'}],
            [{'quantity': 1}], [{'product_size': m, 'quantity': 1}, {'product_size': m, 'quantity': 1}],
            'hoodie', [{'product_size': m, 'quantity': 1}] * 21,
        ]
        for items in bad:
            with self.subTest(items=str(items)[:50]):
                response = self.order(items=items)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertEqual(response.json()['code'], 'validation_error')
        self.assert_nothing_sold()

    def test_requires_login_and_idempotency_key(self):
        response = self.client.post(ORDERS, {'items': [{'product_size': self.medium.id}]}, format='json')
        self.assert_error(response, 400, 'idempotency_key_required')
        self.client.credentials()
        self.assert_error(self.order(), 401, 'not_authenticated')
        self.assert_nothing_sold()


class ProductManagementTests(ShopTestCase):
    def setUp(self):
        super().setUp()
        self.treasurer = self.make_role_user('treasurer')
        self.login_as(self.treasurer)

    def test_staff_create_a_product_with_four_empty_sizes(self):
        response = self.client.post(PRODUCTS, {'name': 'T-Shirt', 'base_price': 40000, 'stock': 99}, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual([(s['size'], s['stock']) for s in response.json()['sizes']], [('S', 0), ('M', 0), ('L', 0), ('XL', 0)])

    def test_restock_adds_stock_with_a_movement_and_an_audit_row(self):
        AuditLog.objects.all()   # rows from the fixture's own restocks exist; count from here
        before = AuditLog.objects.count()

        response = self.client.post(f'{PRODUCTS}/{self.hoodie.id}/restock', {'size': 'M', 'quantity': 7}, format='json')

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.stock_of(self.medium), 12)
        movement = StockMovement.objects.filter(product_size=self.medium).order_by('-id').first()
        self.assertEqual((movement.delta, movement.reason), (7, 'restock'))
        self.assertEqual(AuditLog.objects.count(), before + 1)
        log = AuditLog.objects.order_by('-id').first()
        self.assertEqual((log.actor, log.action), (self.treasurer, 'stock.restocked'))
        self.assertEqual((log.before, log.after), ({'stock': 5}, {'stock': 12, 'added': 7}))
        self.assertEqual(stock.stock_mismatches(), [])

    def test_invalid_restocks_are_refused(self):
        for body in [{'size': 'M', 'quantity': 0}, {'size': 'M', 'quantity': -5}, {'size': 'XXL', 'quantity': 1}, {'size': 'M'}]:
            with self.subTest(body=body):
                response = self.client.post(f'{PRODUCTS}/{self.hoodie.id}/restock', body, format='json')
                self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(self.stock_of(self.medium), 5)

    def test_patch_edits_price_but_cannot_touch_stock(self):
        response = self.client.patch(f'{PRODUCTS}/{self.hoodie.id}', {'base_price': 130000, 'stock': 500, 'sizes': []}, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        self.hoodie.refresh_from_db()
        self.assertEqual(self.hoodie.base_price, 130000)
        self.assertEqual(self.stock_of(self.medium), 5)

    def test_invalid_products_are_refused(self):
        for body, field in [({'name': '', 'base_price': 100}, 'name'), ({'name': 'Cap', 'base_price': 0}, 'base_price'),
                            ({'name': 'Hoodie', 'base_price': 100}, 'name'), ({'name': 'Cap', 'base_price': 100, 'image': 'not a url'}, 'image')]:
            with self.subTest(body=body):
                self.assert_error(self.client.post(PRODUCTS, body, format='json'), 400, 'validation_error', field=field)

    def test_only_president_treasurer_and_event_manager_manage_the_shop(self):
        for role, allowed in [('president', True), ('event_manager', True), ('volunteer_coordinator', False), ('member', False)]:
            with self.subTest(role=role):
                self.login_as(self.make_role_user(role))
                responses = [
                    self.client.post(PRODUCTS, {'name': f'Item {role}', 'base_price': 100}, format='json'),
                    self.client.patch(f'{PRODUCTS}/{self.hoodie.id}', {'description': role}, format='json'),
                    self.client.post(f'{PRODUCTS}/{self.hoodie.id}/restock', {'size': 'S', 'quantity': 1}, format='json'),
                ]
                for response in responses:
                    if allowed:
                        self.assertIn(response.status_code, (200, 201), response.content)
                    else:
                        self.assert_error(response, 403, 'permission_denied')
        self.assertEqual(self.stock_of(size_of(self.hoodie, 'S')), 5)   # 3 + one each from the two allowed roles
        self.login_as(self.user)
        self.assert_error(self.client.post(f'{PRODUCTS}/{self.hoodie.id}/restock', {'size': 'S', 'quantity': 1}, format='json'), 403, 'permission_denied')
