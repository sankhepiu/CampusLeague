from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from common.testing import ApiTestCase
from events.models import Event, Ticket, TicketTier
from events.tests.helpers import make_event, make_member, make_tier
from events.tickets import read_token
from finance.models import LedgerEntry
from finance.services import account_balance
from shop.models import Order, OrderLine, Payment

KEY = 'ticket-key-0001'
OTHER_KEY = 'ticket-key-0002'


class TicketTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.event = make_event()
        self.tier = make_tier(self.event, capacity=10)
        self.user = self.make_user()
        self.login_as(self.user)

    def buy(self, key=KEY, event=None, **body):
        body.setdefault('tier', self.tier.id)
        return self.client.post(
            f'/api/events/{(event or self.event).id}/tickets', body, format='json',
            headers={'Idempotency-Key': key},
        )

    def sold(self):
        self.tier.refresh_from_db()
        return self.tier.sold_count

    def assert_nothing_sold(self, orders=0):
        self.assertEqual(self.sold(), 0)
        self.assertEqual(Ticket.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(LedgerEntry.objects.count(), 0)
        self.assertEqual(Order.objects.count(), orders)


class PurchaseTests(TicketTestCase):
    def test_non_member_pays_public_price_and_gets_a_ticket(self):
        response = self.buy()

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        ticket = Ticket.objects.get()
        self.assertEqual(body['order']['status'], 'paid')
        self.assertEqual(body['order']['total'], 80000)
        self.assertEqual(body['payment']['amount'], 80000)
        self.assertEqual(len(body['tickets']), 1)
        self.assertEqual(body['tickets'][0]['code'], ticket.code)
        self.assertEqual(body['tickets'][0]['qr_token'], ticket.qr_token)
        self.assertEqual(body['tickets'][0]['price_paid'], 80000)
        self.assertEqual(body['tickets'][0]['event']['title'], 'Spring Gala')
        self.assertEqual((ticket.owner, ticket.event, ticket.tier), (self.user, self.event, self.tier))
        self.assertEqual(ticket.status, 'valid')
        self.assertEqual(self.sold(), 1)

    def test_active_member_pays_member_price(self):
        make_member(self.user)
        response = self.buy()
        self.assertEqual(response.json()['order']['total'], 60000)
        self.assertEqual(Ticket.objects.get().price_paid, 60000)
        self.assertEqual(account_balance('4100'), 60000)

    def test_lapsed_member_pays_public_price(self):
        make_member(self.user, days_left=-1)
        self.assertEqual(self.buy().json()['order']['total'], 80000)

    def test_membership_ending_today_still_gets_member_price(self):
        make_member(self.user, days_left=0)
        self.assertEqual(self.buy().json()['order']['total'], 60000)

    def test_price_sent_by_the_client_is_ignored(self):
        response = self.buy(price=1, unit_price=1, total=1, price_paid=1, member=True, is_member=True)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(Payment.objects.get().amount, 80000)
        self.assertEqual(Ticket.objects.get().price_paid, 80000)

    def test_several_tickets_in_one_order(self):
        response = self.buy(quantity=3)

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['order']['total'], 240000)
        self.assertEqual(Ticket.objects.count(), 3)
        self.assertEqual(len(set(Ticket.objects.values_list('code', flat=True))), 3)
        self.assertEqual(self.sold(), 3)

    def test_ledger_entry_per_order_line_tagged_with_the_event(self):
        self.buy(quantity=2)

        entry, line = LedgerEntry.objects.get(), OrderLine.objects.get()
        self.assertEqual((entry.source_type, entry.source_id, entry.kind), ('order_line', line.id, 'ticket_sale'))
        self.assertEqual(entry.event, self.event)
        self.assertEqual(
            sorted(entry.lines.values_list('account__code', 'debit', 'credit')),
            [('1000', 160000, 0), ('4100', 0, 160000)],
        )
        self.assertEqual(account_balance('4000'), 0)   # not dues revenue

    def test_replay_returns_the_same_tickets_and_sells_nothing_more(self):
        first = self.buy()
        replay = self.buy()

        self.assertEqual(replay.status_code, 200, replay.content)
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(Ticket.objects.count(), 1)
        self.assertEqual(self.sold(), 1)
        self.assertEqual(account_balance('1000'), 80000)

    def test_same_key_with_a_different_quantity_is_a_conflict(self):
        self.buy(quantity=1)
        self.assert_error(self.buy(quantity=2), 409, 'idempotency_key_reused')
        self.assertEqual(self.sold(), 1)

    def test_failed_payment_takes_no_seat(self):
        self.assert_error(self.buy(test_outcome='failure'), 402, 'payment_failed')
        self.assert_nothing_sold(orders=1)
        self.assertEqual(Order.objects.get().status, 'cancelled')

    def test_pending_payment_takes_no_seat(self):
        response = self.buy(test_outcome='pending')
        self.assertEqual(response.status_code, 202, response.content)
        self.assertEqual(response.json()['tickets'], [])
        self.assert_nothing_sold(orders=1)

    def test_my_tickets_lists_only_mine(self):
        self.buy()
        other = self.make_user(email='ravi@example.com', name='Ravi', college_id='SSA-002')
        self.login_as(other)
        self.buy(key=OTHER_KEY)

        mine = self.client.get('/api/tickets/me').json()

        self.assertEqual(mine['count'], 1)
        self.assertEqual(mine['results'][0]['code'], Ticket.objects.get(owner=other).code)
        self.client.credentials()
        self.assert_error(self.client.get('/api/tickets/me'), 401, 'not_authenticated')


class SeatLimitTests(TicketTestCase):
    """R8: "sale stops when sold out; no overselling"."""

    def test_last_seat_can_be_bought_and_the_next_buyer_is_told_sold_out(self):
        TicketTier.objects.filter(pk=self.tier.pk).update(sold_count=9)

        self.assertEqual(self.buy(key=KEY).status_code, 201)
        response = self.buy(key=OTHER_KEY)

        self.assert_error(response, 409, 'sold_out')
        self.assertEqual(self.sold(), 10)
        self.assertEqual(Ticket.objects.count(), 1)
        self.assertEqual(Order.objects.count(), 1)   # no order for the refused buyer

    def test_asking_for_more_than_is_left_sells_none(self):
        TicketTier.objects.filter(pk=self.tier.pk).update(sold_count=8)
        self.assert_error(self.buy(quantity=3), 409, 'sold_out')
        self.assertEqual(self.sold(), 8)
        self.assertEqual(Ticket.objects.count(), 0)

    def test_exactly_the_remaining_seats_can_be_bought(self):
        TicketTier.objects.filter(pk=self.tier.pk).update(sold_count=8)
        self.assertEqual(self.buy(quantity=2).status_code, 201)
        self.assertEqual(self.sold(), 10)

    def test_database_refuses_sold_count_above_capacity(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            TicketTier.objects.filter(pk=self.tier.pk).update(sold_count=11)
        self.assertEqual(self.sold(), 0)

    def test_seats_left_is_shown_and_goes_down(self):
        self.buy(quantity=4)
        event = self.client.get(f'/api/events/{self.event.id}').json()
        self.assertEqual(event['tiers'][0]['seats_left'], 6)


class SaleRulesTests(TicketTestCase):
    def test_draft_event_cannot_be_bought_and_looks_missing(self):
        Event.objects.filter(pk=self.event.pk).update(status='draft')
        self.assert_error(self.buy(), 404, 'not_found')
        self.assert_nothing_sold()

    def test_closed_event_cannot_be_bought(self):
        Event.objects.filter(pk=self.event.pk).update(status='closed')
        self.assert_error(self.buy(), 409, 'sales_closed')
        self.assert_nothing_sold()

    def test_sale_window(self):
        now = timezone.now()
        cases = [
            ({'sale_opens': now + timedelta(hours=1)}, 409),
            ({'sale_closes': now - timedelta(hours=1)}, 409),
            ({'sale_opens': now - timedelta(hours=1), 'sale_closes': now + timedelta(hours=1)}, 201),
        ]
        for number, (window, expected) in enumerate(cases):
            with self.subTest(window=window):
                TicketTier.objects.filter(pk=self.tier.pk).update(sale_opens=None, sale_closes=None)
                TicketTier.objects.filter(pk=self.tier.pk).update(**window)
                self.assertEqual(self.buy(key=f'window-key-{number:03}').status_code, expected)

    def test_tier_of_another_event_is_refused(self):
        other_tier = make_tier(make_event(title='Meetup'))
        response = self.buy(tier=other_tier.id)
        self.assert_error(response, 400, 'validation_error', field='tier')
        self.assert_nothing_sold()

    def test_bad_quantities_are_refused(self):
        for quantity in [0, -1, 11, 'two', 1.5, None]:
            with self.subTest(quantity=quantity):
                self.assert_error(self.buy(quantity=quantity), 400, 'validation_error', field='quantity')
        self.assert_nothing_sold()

    def test_requires_login_and_idempotency_key(self):
        response = self.client.post(f'/api/events/{self.event.id}/tickets', {'tier': self.tier.id}, format='json')
        self.assert_error(response, 400, 'idempotency_key_required')
        self.client.credentials()
        self.assert_error(self.buy(), 401, 'not_authenticated')
        self.assert_nothing_sold()

    def test_unknown_event_is_404(self):
        response = self.client.post(
            '/api/events/999999/tickets', {'tier': self.tier.id}, format='json',
            headers={'Idempotency-Key': KEY},
        )
        self.assert_error(response, 404, 'not_found')


class QrTokenTests(TicketTestCase):
    def test_token_carries_ticket_and_event_ids(self):
        self.buy()
        ticket = Ticket.objects.get()
        self.assertEqual(read_token(ticket.qr_token), (ticket.id, self.event.id))

    def test_tampered_or_invented_tokens_do_not_verify(self):
        self.buy()
        token = Ticket.objects.get().qr_token
        payload, _, signature = token.partition(':')
        forgeries = [
            token[:-1] + ('A' if token[-1] != 'A' else 'B'),   # signature changed
            'x' + token,                                        # payload changed
            payload,                                            # signature removed
            payload + ':' + 'A' * len(signature),               # signature invented
            '', 'not-a-token', '1:2:3',
        ]
        for forged in forgeries:
            with self.subTest(forged=forged[:20]):
                self.assertIsNone(read_token(forged))

    def test_token_signed_with_another_secret_does_not_verify(self):
        self.buy()
        token = Ticket.objects.get().qr_token
        with self.settings(SECRET_KEY='a-completely-different-secret'):
            self.assertIsNone(read_token(token))
