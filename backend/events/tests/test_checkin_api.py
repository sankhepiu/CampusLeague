import threading

from django.db import IntegrityError, connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from accounts.models import RoleAssignment, User
from common.testing import ApiTestCase
from events.models import CheckIn, Ticket
from events.tests.helpers import make_event, make_member, make_tier
from events.tickets import scan, sign_ticket
from shop.payments import purchase_tickets

CHECKIN = '/api/checkin'


class CheckInTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.event = make_event()
        self.tier = make_tier(self.event)
        self.holder = self.make_user()
        self.ticket = purchase_tickets(
            user=self.holder, tier_id=self.tier.id, quantity=1,
            outcome='success', idempotency_key='holder-key-01',
        ).tickets[0]
        self.manager = self.make_role_user('event_manager')
        self.login_as(self.manager)

    def scan(self, **body):
        if not body:
            body = {'token': self.ticket.qr_token}
        response = self.client.post(CHECKIN, body, format='json')
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()


class CheckInTests(CheckInTestCase):
    def test_valid_ticket_is_checked_in(self):
        body = self.scan()

        self.assertEqual(body['result'], 'ok')
        self.assertEqual(body['holder_name'], 'Priya')
        self.assertEqual(body['ticket']['code'], self.ticket.code)
        self.assertEqual(body['ticket']['status'], 'checked_in')
        self.assertEqual(body['ticket']['event']['title'], 'Spring Gala')
        self.assertEqual(body['checked_in_by'], self.manager.name)
        checkin = CheckIn.objects.get()
        self.assertEqual((checkin.ticket, checkin.scanned_by), (self.ticket, self.manager))
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'checked_in')

    def test_second_scan_is_rejected_with_the_original_time_and_operator(self):
        first = self.scan()
        president = self.make_role_user('president')
        self.login_as(president)

        second = self.scan()

        self.assertEqual(second['result'], 'already_checked_in')
        self.assertEqual(second['checked_in_at'], first['checked_in_at'])
        self.assertEqual(second['checked_in_by'], self.manager.name)   # not the president
        self.assertEqual(CheckIn.objects.count(), 1)

    def test_database_refuses_a_second_checkin_row(self):
        self.scan()
        with self.assertRaises(IntegrityError), transaction.atomic():
            CheckIn.objects.create(
                ticket=self.ticket, scanned_by=self.manager, scanned_at=timezone.now(),
                member_status_at_scan='none',
            )
        self.assertEqual(CheckIn.objects.count(), 1)

    def test_manual_code_works_in_any_case_and_with_dashes(self):
        code = self.ticket.code
        body = self.scan(code=f' {code[:4].lower()}-{code[4:].lower()} ')
        self.assertEqual(body['result'], 'ok')

    def test_code_after_token_is_still_a_duplicate(self):
        self.scan()
        self.assertEqual(self.scan(code=self.ticket.code)['result'], 'already_checked_in')
        self.assertEqual(CheckIn.objects.count(), 1)

    # Membership status at the door (R5) ---------------------------------

    def test_holder_without_membership_shows_none(self):
        self.assertEqual(self.scan()['membership_status'], 'none')
        self.assertEqual(CheckIn.objects.get().member_status_at_scan, 'none')

    def test_active_member_shows_active(self):
        make_member(self.holder)
        self.assertEqual(self.scan()['membership_status'], 'active')

    def test_lapsed_member_does_not_show_as_active(self):
        make_member(self.holder, days_left=-1)
        body = self.scan()
        self.assertEqual(body['result'], 'ok')              # the ticket is still good
        self.assertEqual(body['membership_status'], 'lapsed')
        self.assertEqual(CheckIn.objects.get().member_status_at_scan, 'lapsed')

    def test_duplicate_reports_the_status_recorded_at_the_first_scan(self):
        self.scan()
        make_member(self.holder)   # joins after being checked in
        self.assertEqual(self.scan()['membership_status'], 'none')

    # Forged, wrong and cancelled tickets --------------------------------

    def assert_invalid(self, **body):
        result = self.scan(**body)
        self.assertEqual(result['result'], 'invalid')
        self.assertIsNone(result['ticket'])
        self.assertIsNone(result['holder_name'])
        self.assertIsNone(result['membership_status'])
        self.assertEqual(CheckIn.objects.count(), 0)

    def test_tampered_token_is_invalid(self):
        token = self.ticket.qr_token
        self.assert_invalid(token=token[:-1] + ('A' if token[-1] != 'A' else 'B'))

    def test_garbage_token_is_invalid(self):
        self.assert_invalid(token='definitely-not-a-ticket')

    def test_correctly_signed_token_for_a_ticket_that_does_not_exist_is_invalid(self):
        self.assert_invalid(token=sign_ticket(999999, self.event.id))

    def test_correctly_signed_token_naming_the_wrong_event_is_invalid(self):
        other = make_event(title='Meetup')
        self.assert_invalid(token=sign_ticket(self.ticket.id, other.id))

    def test_unknown_code_is_invalid(self):
        self.assert_invalid(code='ZZZZZZZZ')

    def test_ticket_for_another_event_is_invalid_at_this_door(self):
        other = make_event(title='Meetup')
        self.assert_invalid(token=self.ticket.qr_token, event=other.id)
        self.assertEqual(self.scan(event=self.event.id, token=self.ticket.qr_token)['result'], 'ok')

    def test_cancelled_ticket_is_not_admitted(self):
        Ticket.objects.filter(pk=self.ticket.pk).update(status='cancelled')
        body = self.scan()
        self.assertEqual(body['result'], 'cancelled')
        self.assertEqual(body['holder_name'], 'Priya')
        self.assertEqual(CheckIn.objects.count(), 0)

    def test_token_and_code_together_or_neither_is_a_400(self):
        for body in [{}, {'token': '', 'code': ''}, {'token': self.ticket.qr_token, 'code': self.ticket.code}]:
            with self.subTest(body=list(body)):
                response = self.client.post(CHECKIN, body, format='json')
                self.assert_error(response, 400, 'validation_error')
        self.assertEqual(CheckIn.objects.count(), 0)


class CheckInPermissionTests(CheckInTestCase):
    def test_only_president_and_event_manager_may_scan(self):
        for role, allowed in [
            ('president', True), ('treasurer', False), ('volunteer_coordinator', False), ('member', False),
        ]:
            with self.subTest(role=role):
                self.login_as(self.make_role_user(role))
                response = self.client.post(CHECKIN, {'token': 'x'}, format='json')
                if allowed:
                    self.assertEqual(response.status_code, 200)
                else:
                    self.assert_error(response, 403, 'permission_denied')

    def test_ticket_holder_cannot_check_themselves_in(self):
        self.login_as(self.holder)
        response = self.client.post(CHECKIN, {'token': self.ticket.qr_token}, format='json')
        self.assert_error(response, 403, 'permission_denied')
        self.assertEqual(CheckIn.objects.count(), 0)

    def test_event_manager_whose_term_ended_is_refused(self):
        RoleAssignment.objects.filter(user=self.manager).delete()
        self.give_role(self.manager, 'event_manager', start_offset=-400, end_offset=-1)
        response = self.client.post(CHECKIN, {'token': self.ticket.qr_token}, format='json')
        self.assert_error(response, 403, 'permission_denied')
        self.assertEqual(CheckIn.objects.count(), 0)

    def test_not_logged_in_is_401(self):
        self.client.credentials()
        self.assert_error(self.client.post(CHECKIN, {'token': 'x'}, format='json'), 401, 'not_authenticated')


class ConcurrentScanTests(TransactionTestCase):
    """Plan: "Scan one ticket twice quickly; one CheckIn row exists"."""

    serialized_rollback = True

    def test_simultaneous_scans_of_one_ticket_admit_once(self):
        event = make_event()
        tier = make_tier(event)
        holder = User.objects.create_user(
            email='priya@example.com', password='correct-horse-battery', name='Priya', college_id='SSA-001',
        )
        operator = User.objects.create_user(
            email='door@example.com', password='correct-horse-battery', name='Door', college_id='SSA-002',
        )
        ticket = purchase_tickets(
            user=holder, tier_id=tier.id, quantity=1, outcome='success', idempotency_key='scan-race-key',
        ).tickets[0]

        scanners = 8
        barrier = threading.Barrier(scanners)
        results = []

        def worker():
            try:
                barrier.wait(timeout=10)
                results.append(scan(operator=operator, token=ticket.qr_token).result)
            except Exception as exc:
                results.append(exc)
            finally:
                connection.close()

        threads = [threading.Thread(target=worker) for _ in range(scanners)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertEqual(sorted(results, key=str), ['already_checked_in'] * (scanners - 1) + ['ok'])
        self.assertEqual(CheckIn.objects.count(), 1)
