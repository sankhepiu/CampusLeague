import importlib
import threading
from datetime import timedelta

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone

from common.testing import ApiTestCase
from events import tickets
from events.models import CheckIn, Ticket, TicketPass
from events.tests.helpers import make_event, make_member, make_tier
from finance.services import account_balance
from shop.payments import purchase_tickets

User = get_user_model()

CHECKIN = '/api/checkin'


class PassTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.event = make_event()
        self.tier = make_tier(self.event, capacity=20)
        self.buyer = self.make_user()
        self.door = self.make_role_user('event_manager')

    def buy(self, quantity=4, user=None, tier=None, key='pass-key-0001'):
        result = purchase_tickets(
            user=user or self.buyer, tier_id=(tier or self.tier).pk, quantity=quantity, outcome='success',
            idempotency_key=key,
        )
        return TicketPass.objects.get(order=result.order)

    def scan(self, **body):
        self.login_as(self.door)
        response = self.client.post(CHECKIN, body, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()


class PurchaseCreatesPassTests(PassTestCase):
    def test_n_tickets_and_one_pass(self):
        self.login_as(self.buyer)
        response = self.client.post(
            f'/api/events/{self.event.id}/tickets', {'tier': self.tier.id, 'quantity': 4}, format='json',
            headers={'Idempotency-Key': 'pass-key-0001'},
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        ticket_pass = TicketPass.objects.get()
        # Seat counting is unchanged: one row per seat.
        self.assertEqual(Ticket.objects.count(), 4)
        self.assertEqual(Ticket.objects.filter(ticket_pass=ticket_pass).count(), 4)
        self.tier.refresh_from_db()
        self.assertEqual(self.tier.sold_count, 4)
        self.assertEqual((ticket_pass.owner, ticket_pass.event, ticket_pass.tier), (self.buyer, self.event, self.tier))

        self.assertEqual(len(body['tickets']), 4)
        self.assertEqual(body['pass']['pass_id'], ticket_pass.id)
        self.assertEqual(body['pass']['qr_token'], ticket_pass.qr_token)
        self.assertEqual((body['pass']['quantity'], body['pass']['admitted'], body['pass']['remaining']), (4, 0, 4))

        # A replay returns the same pass and makes no second one.
        again = self.client.post(
            f'/api/events/{self.event.id}/tickets', {'tier': self.tier.id, 'quantity': 4}, format='json',
            headers={'Idempotency-Key': 'pass-key-0001'},
        )
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()['pass'], body['pass'])
        self.assertEqual(TicketPass.objects.count(), 1)

    def test_pending_and_failed_purchases_have_no_pass(self):
        self.login_as(self.buyer)
        response = self.client.post(
            f'/api/events/{self.event.id}/tickets', {'tier': self.tier.id, 'test_outcome': 'pending'}, format='json',
            headers={'Idempotency-Key': 'pass-key-0002'},
        )
        self.assertEqual(response.status_code, 202)
        self.assertIsNone(response.json()['pass'])
        self.assertEqual(TicketPass.objects.count(), 0)

    def test_pass_token_is_signed_and_not_interchangeable(self):
        ticket_pass = self.buy(1)
        ticket = Ticket.objects.get()
        self.assertEqual(tickets.read_pass_token(ticket_pass.qr_token), (ticket_pass.id, self.event.id))
        self.assertNotEqual(ticket_pass.qr_token, ticket.qr_token)
        # Each kind of token is rejected by the other readers.
        self.assertIsNone(tickets.read_token(ticket_pass.qr_token))
        self.assertIsNone(tickets.read_member_token(ticket_pass.qr_token))
        self.assertIsNone(tickets.read_pass_token(ticket.qr_token))
        self.assertIsNone(tickets.read_pass_token(tickets.sign_member(self.buyer.id)))

    def test_two_purchases_are_two_passes(self):
        first = self.buy(2)
        second = self.buy(3, key='pass-key-0003')
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(sorted(p.tickets.count() for p in TicketPass.objects.all()), [2, 3])


class MyPassesTests(PassTestCase):
    def test_tickets_me_lists_my_passes(self):
        ticket_pass = self.buy(3)
        other = self.make_user(email='ravi@example.com', college_id='SSA-002')
        self.buy(1, user=other, key='pass-key-0009')
        self.scan(token=ticket_pass.qr_token)

        self.login_as(self.buyer)
        body = self.client.get('/api/tickets/me').json()
        self.assertEqual(body['count'], 1)
        item = body['results'][0]
        self.assertEqual(set(item), {
            'pass_id', 'event', 'tier', 'quantity', 'admitted', 'remaining', 'qr_token', 'tickets', 'created_at',
        })
        self.assertEqual(item['pass_id'], ticket_pass.id)
        self.assertEqual(item['event']['id'], self.event.id)
        self.assertEqual((item['event']['name'], item['event']['title'], item['event']['venue']),
                         ('Spring Gala', 'Spring Gala', 'Main Hall'))
        self.assertIn('starts_at', item['event'])
        self.assertEqual(item['tier'], {'id': self.tier.id, 'name': 'General'})
        self.assertEqual((item['quantity'], item['admitted'], item['remaining']), (3, 1, 2))
        self.assertEqual(item['qr_token'], ticket_pass.qr_token)
        rows = list(Ticket.objects.filter(ticket_pass=ticket_pass).order_by('id'))
        self.assertEqual(item['tickets'], [
            {'id': rows[0].id, 'code': rows[0].code, 'status': 'checked_in'},
            {'id': rows[1].id, 'code': rows[1].code, 'status': 'valid'},
            {'id': rows[2].id, 'code': rows[2].code, 'status': 'valid'},
        ])

    def test_listing_many_passes_does_not_cost_a_query_per_pass(self):
        for number in range(6):
            self.buy(2, key=f'pass-key-1{number:03}')
        self.login_as(self.buyer)
        # The login token, the count, the page of passes, and all their
        # tickets in one query: four, however many passes there are.
        with self.assertNumQueries(4):
            body = self.client.get('/api/tickets/me').json()
        self.assertEqual(body['count'], 6)


class PassCheckInTests(PassTestCase):
    def test_each_scan_admits_the_next_ticket(self):
        ticket_pass = self.buy(3)
        first = self.scan(token=ticket_pass.qr_token)
        self.assertEqual(first, {
            'result': 'admitted', 'pass_id': ticket_pass.id, 'admitted': 1, 'admitted_now': 1, 'total': 3,
            'remaining': 2, 'holder': {'name': 'Priya'}, 'membership_status': 'none',
            'event': {'id': self.event.id, 'name': 'Spring Gala', 'title': 'Spring Gala'},
            'tier': {'id': self.tier.id, 'name': 'General'},
        })
        second = self.scan(token=ticket_pass.qr_token)
        self.assertEqual((second['result'], second['admitted'], second['remaining']), ('admitted', 2, 1))
        third = self.scan(pass_token=ticket_pass.qr_token)          # the explicit field works too
        self.assertEqual((third['result'], third['admitted'], third['remaining']), ('admitted', 3, 0))

        # Tickets are used in id order, one CheckIn row each.
        self.assertEqual(Ticket.objects.filter(status='checked_in').count(), 3)
        self.assertEqual(CheckIn.objects.filter(scanned_by=self.door).count(), 3)

        fourth = self.scan(token=ticket_pass.qr_token)
        self.assertEqual((fourth['result'], fourth['admitted'], fourth['total'], fourth['remaining']),
                         ('already_used', 3, 3, 0))
        self.assertEqual(fourth['admitted_now'], 0)
        self.assertEqual(CheckIn.objects.count(), 3)

    def test_count_admits_several_at_once(self):
        ticket_pass = self.buy(10)
        body = self.scan(token=ticket_pass.qr_token, count=3)
        self.assertEqual((body['result'], body['admitted'], body['admitted_now'], body['total'], body['remaining']),
                         ('admitted', 3, 3, 10, 7))
        body = self.scan(token=ticket_pass.qr_token, count=7)
        self.assertEqual((body['admitted'], body['remaining']), (10, 0))
        self.assertEqual(CheckIn.objects.count(), 10)

    def test_count_above_what_is_left_admits_nobody(self):
        ticket_pass = self.buy(3)
        self.scan(token=ticket_pass.qr_token)
        self.login_as(self.door)
        response = self.client.post(CHECKIN, {'token': ticket_pass.qr_token, 'count': 3}, format='json')
        body = self.assert_error(response, 400, 'validation_error', 'count')
        self.assertIn(('count', 'exceeds_remaining'), self.field_codes(body))
        self.assertIn('Only 2 left', body['message'])
        self.assertEqual(CheckIn.objects.count(), 1)
        for bad in [0, -1, 11, 'two']:
            with self.subTest(count=bad):
                response = self.client.post(CHECKIN, {'token': ticket_pass.qr_token, 'count': bad}, format='json')
                self.assert_error(response, 400, 'validation_error', 'count')
        self.assertEqual(CheckIn.objects.count(), 1)

    def test_wrong_event(self):
        ticket_pass = self.buy(2)
        other = make_event(title='Other')
        body = self.scan(token=ticket_pass.qr_token, event=other.id)
        self.assertEqual(body['result'], 'wrong_event')
        self.assertIsNone(body['admitted'])
        self.assertEqual(CheckIn.objects.count(), 0)
        self.assertEqual(self.scan(token=ticket_pass.qr_token, event=self.event.id)['result'], 'admitted')

    def test_tampered_or_forged_pass_tokens_are_invalid(self):
        ticket_pass = self.buy(2)
        token = ticket_pass.qr_token
        forged = [
            token[:-1] + ('a' if token[-1] != 'a' else 'b'),
            tickets.sign_pass(ticket_pass.id + 999, self.event.id),     # correctly signed, no such pass
            tickets.sign_pass(ticket_pass.id, self.event.id + 1),       # correctly signed, wrong event inside
        ]
        for bad in forged:
            with self.subTest(token=bad[-12:]):
                self.assertEqual(self.scan(pass_token=bad)['result'], 'invalid')
        self.assertEqual(CheckIn.objects.count(), 0)

    def test_old_per_ticket_tokens_and_codes_still_work_and_count_on_the_pass(self):
        ticket_pass = self.buy(3)
        first, second, third = Ticket.objects.filter(ticket_pass=ticket_pass).order_by('id')
        body = self.scan(token=second.qr_token)
        self.assertEqual((body['result'], body['ticket']['code'], body['holder_name']), ('ok', second.code, 'Priya'))
        self.assertEqual(self.scan(code=third.code)['result'], 'ok')
        self.assertEqual(self.scan(token=second.qr_token)['result'], 'already_checked_in')

        # The pass has one left, and it is the ticket not yet used.
        body = self.scan(token=ticket_pass.qr_token)
        self.assertEqual((body['result'], body['admitted'], body['remaining']), ('admitted', 3, 0))
        first.refresh_from_db()
        self.assertEqual(first.status, 'checked_in')
        self.assertEqual(self.scan(token=ticket_pass.qr_token)['result'], 'already_used')
        self.assertEqual(CheckIn.objects.count(), 3)

    def test_member_tokens_still_work(self):
        make_member(self.buyer)
        body = self.scan(member_token=tickets.sign_member(self.buyer.id))
        self.assertEqual((body['result'], body['membership_status']), ('member_ok', 'active'))
        # ...and the member's status is reported on a pass scan too.
        self.assertEqual(self.scan(token=self.buy(1).qr_token)['membership_status'], 'active')

    def test_cancelled_tickets_are_not_admitted_or_counted(self):
        ticket_pass = self.buy(3)
        Ticket.objects.filter(pk=ticket_pass.tickets.order_by('id').first().pk).update(status='cancelled')
        body = self.scan(token=ticket_pass.qr_token, count=2)
        self.assertEqual((body['admitted'], body['total'], body['remaining']), (2, 2, 0))
        self.assertEqual(self.scan(token=ticket_pass.qr_token)['result'], 'already_used')
        self.assertEqual(Ticket.objects.filter(status='cancelled').count(), 1)

    def test_only_door_staff_may_scan_a_pass(self):
        ticket_pass = self.buy(2)
        for user in [self.buyer, self.make_role_user('treasurer')]:
            self.login_as(user)
            response = self.client.post(CHECKIN, {'token': ticket_pass.qr_token}, format='json')
            self.assert_error(response, 403, 'permission_denied')
        self.assertEqual(CheckIn.objects.count(), 0)

    def test_exactly_one_token_is_required(self):
        ticket_pass = self.buy(1)
        self.login_as(self.door)
        both = {'pass_token': ticket_pass.qr_token, 'code': Ticket.objects.get().code}
        self.assert_error(self.client.post(CHECKIN, both, format='json'), 400, 'validation_error')
        self.assertEqual(CheckIn.objects.count(), 0)


class PassDetailTests(PassTestCase):
    def test_owner_sees_the_pass_with_its_check_in_history(self):
        ticket_pass = self.buy(5)
        second_door = self.make_role_user('volunteer_coordinator')
        self.scan(token=ticket_pass.qr_token, count=2)
        self.login_as(second_door)
        self.client.post(CHECKIN, {'token': ticket_pass.qr_token}, format='json')

        self.login_as(self.buyer)
        response = self.client.get(f'/api/tickets/passes/{ticket_pass.id}')
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual((body['pass_id'], body['quantity'], body['admitted'], body['remaining']),
                         (ticket_pass.id, 5, 3, 2))
        self.assertEqual(body['order'], ticket_pass.order_id)
        self.assertEqual(body['holder'], {'name': 'Priya'})
        self.assertEqual(len(body['tickets']), 5)
        # Oldest first; the scan of two is one line.
        self.assertEqual([(item['by'], item['count']) for item in body['history']],
                         [('Event_Manager', 2), ('Volunteer_Coordinator', 1)])
        self.assertEqual(set(body['history'][0]), {'at', 'by', 'count'})
        self.assertLessEqual(body['history'][0]['at'], body['history'][1]['at'])
        # Sent in the site's time zone like every other timestamp, not UTC "Z".
        self.assertTrue(all(item['at'].endswith('+05:30') for item in body['history']), body['history'])

    def test_staff_can_open_any_pass_and_others_get_a_404(self):
        ticket_pass = self.buy(1)
        url = f'/api/tickets/passes/{ticket_pass.id}'
        for role in ['president', 'volunteer_coordinator']:
            self.login_as(self.make_role_user(role))
            self.assertEqual(self.client.get(url).status_code, 200, role)
        self.login_as(self.door)
        self.assertEqual(self.client.get(url).status_code, 200)

        self.login_as(self.make_user(email='ravi@example.com', college_id='SSA-002'))
        self.assert_error(self.client.get(url), 404, 'not_found')
        self.login_as(self.make_role_user('treasurer'))
        self.assert_error(self.client.get(url), 404, 'not_found')
        self.client.credentials()
        self.assert_error(self.client.get(url), 401, 'not_authenticated')
        self.login_as(self.buyer)
        self.assert_error(self.client.get('/api/tickets/passes/999999'), 404, 'not_found')


class EventOverviewTests(PassTestCase):
    def test_everyone_gets_the_overview(self):
        vip = make_tier(self.event, name='VIP', public_price=150000, member_price=120000, capacity=5,
                        sale_closes=timezone.now() - timedelta(hours=1))
        ticket_pass = self.buy(4)
        self.buy(1, user=self.make_user(email='ravi@example.com', college_id='SSA-002'), key='pass-key-0005')
        self.scan(token=ticket_pass.qr_token, count=3)

        self.client.credentials()
        body = self.client.get(f'/api/events/{self.event.id}').json()
        self.assertEqual((body['description'], body['venue']), ('', 'Main Hall'))
        self.assertEqual(body['organiser'], {'name': 'Skyline Student Association'})      # no creator recorded
        self.assertEqual((body['capacity'], body['sold'], body['seats_left'], body['checked_in']), (100, 5, 20, 3))
        self.assertEqual(body['my_passes'], [])
        self.assertNotIn('revenue', body)
        self.assertNotIn('attendance_pct', body)
        tiers = {tier['name']: tier for tier in body['tiers']}
        self.assertEqual(
            {key: tiers['General'][key] for key in ['id', 'price', 'member_price', 'capacity', 'sold', 'seats_left', 'sale_open']},
            {'id': self.tier.id, 'price': 80000, 'member_price': 60000, 'capacity': 20, 'sold': 5,
             'seats_left': 15, 'sale_open': True},
        )
        self.assertEqual((tiers['VIP']['id'], tiers['VIP']['sold'], tiers['VIP']['sale_open']), (vip.id, 0, False))

    def test_the_buyer_sees_their_own_passes_and_the_member_price(self):
        make_member(self.buyer)
        ticket_pass = self.buy(2)
        self.buy(1, user=self.make_user(email='ravi@example.com', college_id='SSA-002'), key='pass-key-0005')
        self.login_as(self.buyer)
        body = self.client.get(f'/api/events/{self.event.id}').json()
        self.assertEqual([item['pass_id'] for item in body['my_passes']], [ticket_pass.id])
        self.assertEqual(body['my_passes'][0]['quantity'], 2)
        self.assertEqual(body['tiers'][0]['price'], 60000)
        self.assertNotIn('revenue', body)

    def test_staff_also_get_revenue_and_attendance(self):
        ticket_pass = self.buy(4)
        self.scan(token=ticket_pass.qr_token)
        for role, expected in [('president', True), ('treasurer', False), ('volunteer_coordinator', False)]:
            self.login_as(self.make_role_user(role))
            body = self.client.get(f'/api/events/{self.event.id}').json()
            self.assertEqual('revenue' in body, expected, role)
            self.assertEqual('attendance_pct' in body, expected, role)
        self.login_as(self.door)
        body = self.client.get(f'/api/events/{self.event.id}').json()
        self.assertEqual((body['revenue'], body['attendance_pct']), (320000, 25.0))
        self.assertEqual(body['revenue'], account_balance('4100'))

    def test_attendance_is_null_before_anything_is_sold(self):
        self.login_as(self.door)
        body = self.client.get(f'/api/events/{self.event.id}').json()
        self.assertEqual((body['sold'], body['revenue'], body['attendance_pct']), (0, 0, None))

    def test_organiser_is_whoever_created_the_event(self):
        self.login_as(self.door)
        starts = timezone.now() + timedelta(days=5)
        created = self.client.post('/api/events', {
            'title': 'Quiz Night', 'venue': 'Room 4', 'capacity_total': 30,
            'starts_at': starts.isoformat(), 'ends_at': (starts + timedelta(hours=2)).isoformat(),
            'status': 'on_sale',
        }, format='json')
        self.assertEqual(created.status_code, 201, created.content)
        body = self.client.get(f"/api/events/{created.json()['id']}").json()
        self.assertEqual(body['organiser'], {'name': 'Event_Manager'})

    def test_list_keeps_its_shape_plus_the_new_tier_fields(self):
        body = self.client.get('/api/events').json()['results'][0]
        self.assertNotIn('my_passes', body)
        self.assertNotIn('organiser', body)
        self.assertEqual((body['tiers'][0]['sold'], body['tiers'][0]['sale_open']), (0, True))


class DataMigrationTests(PassTestCase):
    def test_tickets_sold_before_passes_existed_get_one_pass_per_order_and_tier(self):
        other_tier = make_tier(self.event, name='VIP', capacity=5)
        self.buy(3)
        self.buy(2, key='pass-key-0006')
        self.buy(1, tier=other_tier, key='pass-key-0007')
        # Put the data back to how it was before the migration.
        Ticket.objects.update(ticket_pass=None)
        TicketPass.objects.all().delete()

        migration = importlib.import_module('events.migrations.0003_passes_for_existing_tickets')
        migration.create_passes(apps, None)
        migration.create_passes(apps, None)        # running it again changes nothing

        self.assertEqual(TicketPass.objects.count(), 3)
        self.assertFalse(Ticket.objects.filter(ticket_pass__isnull=True).exists())
        self.assertEqual(sorted(p.tickets.count() for p in TicketPass.objects.all()), [1, 2, 3])
        for ticket_pass in TicketPass.objects.all():
            self.assertEqual(ticket_pass.owner, self.buyer)
            self.assertEqual(set(ticket_pass.tickets.values_list('order_id', 'tier_id')),
                             {(ticket_pass.order_id, ticket_pass.tier_id)})
            # The token it was given is one the app accepts.
            self.assertEqual(tickets.read_pass_token(ticket_pass.qr_token), (ticket_pass.id, self.event.id))
        self.assertEqual(self.scan(token=TicketPass.objects.first().qr_token)['result'], 'admitted')


class LastSeatOnAPassRaceTests(TransactionTestCase):
    """Two door scanners read the same pass at the same instant. Threads,
    each with its own connection and committed transaction.
    """

    serialized_rollback = True

    def setUp(self):
        self.tier = make_tier(make_event(), capacity=20)
        self.buyer = User.objects.create_user(email='priya@example.com', name='Priya', college_id='SSA-001')
        self.doors = [
            User.objects.create_user(email=f'door{n}@example.com', name=f'Door {n}', college_id=f'SSA-D{n}')
            for n in range(4)
        ]

    def make_pass(self, quantity):
        result = purchase_tickets(
            user=self.buyer, tier_id=self.tier.pk, quantity=quantity, outcome='success', idempotency_key='race-pass-0001',
        )
        return TicketPass.objects.get(order=result.order)

    def scan_together(self, ticket_pass, scanners, count=1):
        barrier = threading.Barrier(scanners)
        outcomes = [None] * scanners

        def worker(index):
            try:
                barrier.wait(timeout=10)
                outcomes[index] = tickets.scan_pass(
                    operator=self.doors[index], token=ticket_pass.qr_token, count=count,
                )
            except Exception as exc:
                outcomes[index] = exc
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(scanners)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertFalse(any(thread.is_alive() for thread in threads), 'a scan thread hung')
        return outcomes

    def test_the_last_seat_is_admitted_once(self):
        ticket_pass = self.make_pass(3)
        tickets.scan_pass(operator=self.doors[0], token=ticket_pass.qr_token, count=2)

        outcomes = self.scan_together(ticket_pass, 4)

        self.assertEqual(sorted(outcome.result for outcome in outcomes),
                         ['admitted', 'already_used', 'already_used', 'already_used'], outcomes)
        self.assertEqual(CheckIn.objects.count(), 3)
        self.assertEqual(Ticket.objects.filter(status='checked_in').count(), 3)

    def test_four_scanners_and_three_seats(self):
        ticket_pass = self.make_pass(3)
        outcomes = self.scan_together(ticket_pass, 4)
        self.assertEqual(sorted(outcome.result for outcome in outcomes),
                         ['admitted', 'admitted', 'admitted', 'already_used'], outcomes)
        # Each admitted scan reports a different running total.
        self.assertEqual(sorted(o.admitted for o in outcomes if o.result == 'admitted'), [1, 2, 3])
        self.assertEqual(CheckIn.objects.count(), 3)
        self.assertEqual(len(set(CheckIn.objects.values_list('ticket_id', flat=True))), 3)

    def test_two_groups_of_two_cannot_share_three_seats(self):
        ticket_pass = self.make_pass(3)
        outcomes = self.scan_together(ticket_pass, 2, count=2)
        refused = [outcome for outcome in outcomes if isinstance(outcome, Exception)]
        self.assertEqual([type(exc) for exc in refused], [tickets.TooManyForPass], outcomes)
        self.assertEqual(refused[0].remaining, 1)
        self.assertEqual(CheckIn.objects.count(), 2)
