from django.db import connection
from django.test.utils import CaptureQueriesContext

from common.testing import ApiTestCase
from events.tests.helpers import make_event, make_tier
from members.tests.test_services import make_plan
from shop.payments import purchase_membership, purchase_merch, purchase_tickets
from shop.tests.helpers import make_product, size_of

MY_ORDERS = '/api/orders/me'


class OrderLineLabelTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.login_as(self.user)
        self.plan = make_plan(name='Plus', price=90000)
        self.tier = make_tier(make_event(title='Spring Gala'), name='General', capacity=500)
        self.hoodie = make_product('Skyline Hoodie', 120000, {'S': 100, 'M': 100})
        self.tee = make_product('Skyline T-Shirt', 40000, {'XL': 100})
        self.count = 0

    def key(self):
        self.count += 1
        return f'label-key-{self.count:05}'

    def buy_membership(self, **extra):
        return purchase_membership(user=self.user, plan=self.plan, outcome='success', idempotency_key=self.key(), **extra)

    def buy_ticket(self, quantity=1, outcome='success'):
        return purchase_tickets(user=self.user, tier_id=self.tier.id, quantity=quantity, outcome=outcome, idempotency_key=self.key())

    def buy_merch(self, items, outcome='success'):
        return purchase_merch(user=self.user, items=items, outcome=outcome, idempotency_key=self.key())

    def my_lines(self):
        response = self.client.get(MY_ORDERS)
        self.assertEqual(response.status_code, 200, response.content)
        return [line for order in response.json()['results'] for line in order['lines']]

    # The three kinds -------------------------------------------------------

    def test_membership_line_is_labelled_with_the_plan_name(self):
        self.buy_membership()
        (line,) = self.my_lines()
        self.assertEqual((line['kind'], line['label']), ('membership', 'Plus membership'))

    def test_ticket_line_is_labelled_with_event_and_tier(self):
        self.buy_ticket(quantity=2)
        (line,) = self.my_lines()
        self.assertEqual((line['kind'], line['label'], line['qty']), ('ticket', 'Spring Gala · General', 2))

    def test_merch_lines_are_labelled_with_product_and_size(self):
        self.buy_merch({size_of(self.hoodie, 'M').pk: 1, size_of(self.tee, 'XL').pk: 2})
        labels = sorted(line['label'] for line in self.my_lines())
        self.assertEqual(labels, ['Skyline Hoodie · M', 'Skyline T-Shirt · XL'])
        self.assertTrue(all(line['kind'] == 'merch' for line in self.my_lines()))

    def test_all_three_kinds_together_newest_order_first(self):
        self.buy_membership()
        self.buy_ticket()
        self.buy_merch({size_of(self.hoodie, 'S').pk: 1})
        self.assertEqual([(line['kind'], line['label']) for line in self.my_lines()], [
            ('merch', 'Skyline Hoodie · S'),
            ('ticket', 'Spring Gala · General'),
            ('membership', 'Plus membership'),
        ])

    def test_existing_id_fields_are_kept(self):
        self.buy_membership()
        self.buy_ticket()
        self.buy_merch({size_of(self.hoodie, 'M').pk: 1})
        merch, ticket, membership = self.my_lines()

        for line in (merch, ticket, membership):
            self.assertEqual(set(line), {
            'id', 'kind', 'label', 'plan', 'tier', 'product_size', 'qty', 'unit_price', 'discount', 'coupon_discount',
        })
        self.assertEqual((membership['plan'], membership['tier'], membership['product_size']), (self.plan.id, None, None))
        self.assertEqual((ticket['plan'], ticket['tier'], ticket['product_size']), (None, self.tier.id, None))
        self.assertEqual((merch['plan'], merch['tier'], merch['product_size']), (None, None, size_of(self.hoodie, 'M').pk))

    def test_cancelled_and_pending_orders_are_labelled_too(self):
        self.buy_ticket(outcome='failure')
        self.buy_merch({size_of(self.hoodie, 'M').pk: 1}, outcome='pending')
        self.assertEqual(sorted(line['label'] for line in self.my_lines()), ['Skyline Hoodie · M', 'Spring Gala · General'])

    def test_label_follows_a_rename(self):
        # The label is read from the related rows, not copied at purchase time.
        self.buy_ticket()
        self.tier.event.title = 'Spring Gala 2027'
        self.tier.event.save()
        self.assertEqual(self.my_lines()[0]['label'], 'Spring Gala 2027 · General')

    def test_label_cannot_be_set_by_the_client(self):
        response = self.client.post(
            '/api/orders',
            {'items': [{'product_size': size_of(self.hoodie, 'M').pk, 'quantity': 1, 'label': 'Free stuff'}], 'label': 'Free stuff'},
            format='json', headers={'Idempotency-Key': self.key()},
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['order']['lines'][0]['label'], 'Skyline Hoodie · M')

    # The purchase responses use the same serializer ------------------------

    def test_purchase_responses_carry_the_label(self):
        membership = self.client.post('/api/memberships', {'plan': self.plan.id}, format='json', headers={'Idempotency-Key': self.key()})
        ticket = self.client.post(f'/api/events/{self.tier.event_id}/tickets', {'tier': self.tier.id}, format='json', headers={'Idempotency-Key': self.key()})
        self.assertEqual(membership.json()['order']['lines'][0]['label'], 'Plus membership')
        self.assertEqual(ticket.json()['order']['lines'][0]['label'], 'Spring Gala · General')

    def test_another_users_orders_are_not_listed(self):
        self.buy_ticket()
        other = self.make_user(email='ravi@example.com', name='Ravi', college_id='SSA-002')
        self.login_as(other)
        self.assertEqual(self.my_lines(), [])

    # Query count -----------------------------------------------------------

    def queries_for_my_orders(self):
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(MY_ORDERS)
        self.assertEqual(response.status_code, 200)
        return len(captured), response.json()

    def mixed_orders(self, rounds):
        for _ in range(rounds):
            self.buy_membership()
            self.buy_ticket()
            self.buy_merch({size_of(self.hoodie, 'M').pk: 1, size_of(self.tee, 'XL').pk: 1})

    def test_query_count_does_not_grow_with_the_number_of_orders_or_lines(self):
        self.mixed_orders(1)                       # 3 orders, 4 lines
        few, body = self.queries_for_my_orders()
        self.assertEqual(body['count'], 3)

        self.mixed_orders(5)                       # 18 orders, 24 lines
        many, body = self.queries_for_my_orders()
        self.assertEqual(body['count'], 18)
        self.assertEqual(sum(len(order['lines']) for order in body['results']), 24)

        self.assertEqual(many, few)

    def test_exactly_four_queries(self):
        self.mixed_orders(2)
        # 1 token and user, 2 count for pagination, 3 the page of orders,
        # 4 all their lines with plan, tier, event, size and product joined.
        with self.assertNumQueries(4):
            response = self.client.get(MY_ORDERS)
        self.assertTrue(all(line['label'] for order in response.json()['results'] for line in order['lines']))

    def test_a_full_page_of_20_orders_is_still_four_queries(self):
        self.mixed_orders(8)                       # 24 orders: more than one page
        with self.assertNumQueries(4):
            body = self.client.get(MY_ORDERS).json()
        self.assertEqual(len(body['results']), 20)
