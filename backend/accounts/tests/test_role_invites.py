import threading
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.db import IntegrityError, connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from accounts import roles
from accounts.models import RoleAssignment, RoleInvite
from audit.models import AuditLog
from common.testing import ApiTestCase

User = get_user_model()

ROLES = '/api/roles'
INVITES = '/api/roles/invites'


class InviteTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        self.president = self.make_role_user('president')
        self.nominee = self.make_user(email='meera@example.com', name='Meera', college_id='SSA-002')
        self.login_as(self.president)

    def invite(self, **overrides):
        body = {'user': self.nominee.id, 'role': 'event_manager'}
        body.update(overrides)
        return self.client.post(ROLES, body, format='json')

    def act(self, invite_id, action, user=None):
        self.login_as(user or self.nominee)
        return self.client.post(f'{INVITES}/{invite_id}/{action}')


class CreateInviteTests(InviteTestCase):
    def test_invite_is_created_pending_and_grants_nothing(self):
        before = timezone.now()
        response = self.invite()
        self.assertEqual(response.status_code, 201, response.content)
        invite = RoleInvite.objects.get()
        body = response.json()
        self.assertEqual(set(body), {
            'id', 'user', 'role', 'invited_by', 'status', 'term_start', 'term_end',
            'expires_at', 'created_at', 'responded_at',
        })
        self.assertEqual(body['id'], invite.id)
        self.assertEqual(body['user'], {'id': self.nominee.id, 'name': 'Meera', 'email': 'meera@example.com'})
        self.assertEqual(body['invited_by'], {'id': self.president.id, 'name': 'President'})
        self.assertEqual((body['role'], body['status'], body['responded_at']), ('event_manager', 'pending', None))
        # No dates sent: one year from today.
        self.assertEqual(body['term_start'], self.today.isoformat())
        self.assertEqual(body['term_end'], (self.today + timedelta(days=365)).isoformat())
        # Expires 72 hours after it was made.
        self.assertGreaterEqual(invite.expires_at, before + timedelta(hours=72))
        self.assertLessEqual(invite.expires_at, timezone.now() + timedelta(hours=72))

        self.assertEqual(RoleAssignment.objects.filter(user=self.nominee).count(), 0)
        self.assertEqual(self.nominee.current_roles(), [])
        # Still locked out of what the role would allow.
        self.login_as(self.nominee)
        self.assert_error(self.client.post('/api/events', {}, format='json'), 403, 'permission_denied')

    def test_the_nominee_is_emailed(self):
        self.invite()
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ['meera@example.com'])
        self.assertIn('event manager', message.subject)
        self.assertIn('President has nominated you', message.body)
        self.assertIn('72 hours', message.body)

    def test_a_mail_failure_does_not_lose_the_invite(self):
        from unittest import mock

        with mock.patch('accounts.roles.send_mail', side_effect=OSError('smtp down')):
            with self.assertLogs('campusleague.roles', level='ERROR'):
                response = self.invite()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(RoleInvite.objects.filter(status='pending').count(), 1)

    def test_only_a_president_can_invite(self):
        for role in ['treasurer', 'event_manager', 'volunteer_coordinator', 'member']:
            with self.subTest(role=role):
                self.login_as(self.make_role_user(role))
                self.assert_error(self.invite(), 403, 'permission_denied')
        self.login_as(self.nominee)
        self.assert_error(self.invite(), 403, 'permission_denied')
        self.client.credentials()
        self.assert_error(self.invite(), 401, 'not_authenticated')
        self.assertEqual(RoleInvite.objects.count(), 0)
        self.assertEqual(mail.outbox, [])

    def test_inviting_yourself_is_refused(self):
        self.assert_error(self.invite(user=self.president.id, role='treasurer'), 400, 'self_assignment')
        self.assertEqual(RoleInvite.objects.count(), 0)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_the_database_refuses_a_self_invite_too(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            RoleInvite.objects.create(
                user=self.president, invited_by=self.president, role='treasurer',
                term_start=self.today, term_end=self.today, expires_at=timezone.now(),
            )

    def test_a_second_pending_invite_for_the_same_role_is_a_409(self):
        self.assertEqual(self.invite().status_code, 201)
        self.assert_error(self.invite(), 409, 'invite_pending')
        self.assertEqual(RoleInvite.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        # A different role for the same person is a different invite.
        self.assertEqual(self.invite(role='treasurer').status_code, 201)

    def test_after_a_decline_the_person_can_be_invited_again(self):
        first = self.invite().json()['id']
        self.act(first, 'decline')
        self.login_as(self.president)
        self.assertEqual(self.invite().status_code, 201)

    def test_someone_who_already_holds_the_role_is_a_409(self):
        self.give_role(self.nominee, 'event_manager')
        self.assert_error(self.invite(), 409, 'role_already_held')
        self.assertEqual(RoleInvite.objects.count(), 0)

    def test_the_nominee_must_be_a_verified_active_user(self):
        unverified = self.make_user(email='new@example.com', college_id='SSA-003', email_verified=False)
        inactive = self.make_user(email='gone@example.com', college_id='SSA-004', is_active=False)
        for user_id in [unverified.id, inactive.id, 999999]:
            with self.subTest(user=user_id):
                body = self.assert_error(self.invite(user=user_id), 400, 'validation_error', 'user')
                self.assertIn(('user', 'does_not_exist'), self.field_codes(body))
        self.assertEqual(RoleInvite.objects.count(), 0)

    def test_bad_terms_are_refused(self):
        yesterday = (self.today - timedelta(days=1)).isoformat()
        cases = [
            ({'term_start': self.today.isoformat(), 'term_end': yesterday}, 'term_end', 'term_end_before_start'),
            ({'term_start': (self.today - timedelta(days=30)).isoformat(), 'term_end': yesterday}, 'term_end', 'term_in_past'),
            ({'term_start': 'soon'}, 'term_start', 'invalid'),
            ({'role': 'emperor'}, 'role', 'invalid_choice'),
        ]
        for overrides, field, code in cases:
            with self.subTest(overrides=overrides):
                body = self.assert_error(self.invite(**overrides), 400, 'validation_error', field)
                self.assertIn((field, code), self.field_codes(body))
        self.assertEqual(RoleInvite.objects.count(), 0)


class RespondTests(InviteTestCase):
    def setUp(self):
        super().setUp()
        self.invite_id = self.invite(
            term_start=self.today.isoformat(), term_end=(self.today + timedelta(days=100)).isoformat(),
        ).json()['id']

    def test_accept_creates_the_assignment_and_an_audit_row(self):
        response = self.act(self.invite_id, 'accept')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['status'], 'accepted')
        self.assertIsNotNone(response.json()['responded_at'])

        assignment = RoleAssignment.objects.get(user=self.nominee)
        self.assertEqual(
            (assignment.role, assignment.term_start, assignment.term_end),
            ('event_manager', self.today, self.today + timedelta(days=100)),
        )
        self.assertEqual(RoleInvite.objects.get().assignment, assignment)
        self.assertEqual(self.nominee.current_roles(), ['event_manager'])
        log = AuditLog.objects.get(action='role.assigned')
        self.assertEqual((log.actor, log.object_id), (self.nominee, assignment.id))
        # The role now works.
        self.assert_error(self.client.post('/api/events', {}, format='json'), 400, 'validation_error', 'title')

    def test_accepting_twice_gives_one_assignment(self):
        self.act(self.invite_id, 'accept')
        self.assert_error(self.act(self.invite_id, 'accept'), 409, 'invite_not_pending')
        self.assert_error(self.act(self.invite_id, 'decline'), 409, 'invite_not_pending')
        self.assertEqual(RoleAssignment.objects.filter(user=self.nominee).count(), 1)
        self.assertEqual(AuditLog.objects.filter(action='role.assigned').count(), 1)
        self.assertEqual(RoleInvite.objects.get().status, 'accepted')

    def test_if_the_audit_row_cannot_be_written_nothing_is_granted(self):
        from unittest import mock

        with mock.patch('accounts.roles.audit.record', side_effect=RuntimeError('audit down')):
            with self.assertRaises(RuntimeError):
                roles.respond(invite_id=self.invite_id, user=self.nominee, accept=True)
        self.assertEqual(RoleAssignment.objects.filter(user=self.nominee).count(), 0)
        self.assertEqual(RoleInvite.objects.get().status, 'pending')

    def test_decline_grants_nothing(self):
        response = self.act(self.invite_id, 'decline')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['status'], 'declined')
        self.assertEqual(RoleAssignment.objects.filter(user=self.nominee).count(), 0)
        self.assertEqual(AuditLog.objects.filter(action='role.invite_declined').count(), 1)
        self.assert_error(self.act(self.invite_id, 'accept'), 409, 'invite_not_pending')
        self.assertEqual(self.nominee.current_roles(), [])

    def test_only_the_nominee_can_accept_or_decline(self):
        outsider = self.make_user(email='ravi@example.com', college_id='SSA-005')
        treasurer = self.make_role_user('treasurer')
        for action in ['accept', 'decline']:
            with self.subTest(action=action):
                # The president can see the invite but is not the nominee.
                self.assert_error(self.act(self.invite_id, action, self.president), 403, 'not_the_nominee')
                # Others cannot see it at all.
                self.assert_error(self.act(self.invite_id, action, outsider), 404, 'not_found')
                self.assert_error(self.act(self.invite_id, action, treasurer), 404, 'not_found')
                self.client.credentials()
                self.assert_error(self.client.post(f'{INVITES}/{self.invite_id}/{action}'), 401, 'not_authenticated')
        self.assertEqual(RoleInvite.objects.get().status, 'pending')
        self.assertEqual(RoleAssignment.objects.filter(user=self.nominee).count(), 0)

    def test_president_revokes_and_the_invite_can_no_longer_be_accepted(self):
        response = self.act(self.invite_id, 'revoke', self.president)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['status'], 'revoked')
        self.assertEqual(AuditLog.objects.filter(action='role.invite_revoked').count(), 1)
        self.assert_error(self.act(self.invite_id, 'accept'), 409, 'invite_not_pending')
        self.assert_error(self.act(self.invite_id, 'revoke', self.president), 409, 'invite_not_pending')
        self.assertEqual(RoleAssignment.objects.filter(user=self.nominee).count(), 0)

    def test_only_a_president_can_revoke(self):
        self.assert_error(self.act(self.invite_id, 'revoke'), 403, 'permission_denied')      # the nominee
        self.assert_error(self.act(self.invite_id, 'revoke', self.make_role_user('treasurer')), 404, 'not_found')
        self.assertEqual(RoleInvite.objects.get().status, 'pending')

    def test_an_expired_invite_cannot_be_accepted(self):
        RoleInvite.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        self.assert_error(self.act(self.invite_id, 'accept'), 409, 'invite_not_pending')
        self.assertEqual(RoleInvite.objects.get().status, 'expired')
        self.assertEqual(RoleAssignment.objects.filter(user=self.nominee).count(), 0)
        # An expired invite no longer blocks a fresh one.
        self.login_as(self.president)
        self.assertEqual(self.invite().status_code, 201)

    def test_an_invite_one_minute_from_expiry_can_still_be_accepted(self):
        RoleInvite.objects.update(expires_at=timezone.now() + timedelta(minutes=1))
        self.assertEqual(self.act(self.invite_id, 'accept').status_code, 200)

    def test_unknown_invite_is_a_404(self):
        self.assert_error(self.act(999999, 'accept'), 404, 'not_found')


class ListInvitesTests(InviteTestCase):
    def test_president_sees_all_and_others_see_their_own(self):
        other = self.make_user(email='ravi@example.com', name='Ravi', college_id='SSA-005')
        mine = self.invite().json()['id']
        theirs = self.invite(user=other.id, role='treasurer').json()['id']

        body = self.client.get(INVITES).json()
        self.assertEqual(sorted(invite['id'] for invite in body['results']), [mine, theirs])

        self.login_as(self.nominee)
        body = self.client.get(INVITES).json()
        self.assertEqual([invite['id'] for invite in body['results']], [mine])
        self.assertEqual(body['results'][0]['invited_by']['name'], 'President')

        self.login_as(self.make_role_user('treasurer'))
        self.assertEqual(self.client.get(INVITES).json()['count'], 0)
        self.client.credentials()
        self.assert_error(self.client.get(INVITES), 401, 'not_authenticated')

    def test_status_filter_and_expiry_on_read(self):
        invite_id = self.invite().json()['id']
        self.assertEqual(self.client.get(INVITES, {'status': 'pending'}).json()['count'], 1)
        RoleInvite.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get(INVITES, {'status': 'pending'}).json()['count'], 0)
        expired = self.client.get(INVITES, {'status': 'expired'}).json()['results']
        self.assertEqual([invite['id'] for invite in expired], [invite_id])


class EndRoleTests(InviteTestCase):
    def end(self, assignment):
        return self.client.post(f'{ROLES}/{assignment.id}/end')

    def test_ending_a_role_removes_the_access_today(self):
        assignment = self.give_role(self.nominee, 'treasurer')
        response = self.end(assignment)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['assignment']['term_end'], (self.today - timedelta(days=1)).isoformat())
        self.assertEqual(self.nominee.current_roles(), [])
        log = AuditLog.objects.get(action='role.ended')
        self.assertEqual((log.actor, log.object_id), (self.president, assignment.id))

    def test_a_role_that_started_today_is_removed(self):
        assignment = self.give_role(self.nominee, 'treasurer', start_offset=0)
        response = self.end(assignment)
        self.assertEqual(response.json(), {'ended': True, 'assignment': None})
        self.assertFalse(RoleAssignment.objects.filter(pk=assignment.pk).exists())
        self.assertEqual(AuditLog.objects.filter(action='role.ended').count(), 1)

    def test_the_last_president_cannot_be_ended(self):
        own = RoleAssignment.objects.get(user=self.president, role='president')
        self.assert_error(self.end(own), 400, 'last_president')
        own.refresh_from_db()
        self.assertGreater(own.term_end, self.today)
        self.assertEqual(self.president.current_roles(), ['president'])
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_a_president_can_step_down_once_there_is_another(self):
        second = self.make_user(email='next@example.com', college_id='SSA-006')
        self.give_role(second, 'president')
        own = RoleAssignment.objects.get(user=self.president, role='president')
        self.assertEqual(self.end(own).status_code, 200)
        self.assertEqual(self.president.current_roles(), [])
        # ...and now the remaining one is the last.
        self.login_as(second)
        self.assert_error(self.end(RoleAssignment.objects.get(user=second)), 400, 'last_president')

    def test_a_future_or_past_president_does_not_count_as_a_current_one(self):
        elect = self.make_user(email='elect@example.com', college_id='SSA-007')
        former = self.make_user(email='former@example.com', college_id='SSA-008')
        self.give_role(elect, 'president', start_offset=10, end_offset=300)
        self.give_role(former, 'president', start_offset=-300, end_offset=-10)
        own = RoleAssignment.objects.get(user=self.president, role='president')
        self.assert_error(self.end(own), 400, 'last_president')

    def test_only_a_president_can_end_a_role(self):
        assignment = self.give_role(self.nominee, 'treasurer')
        for user in [self.nominee, self.make_role_user('event_manager')]:
            self.login_as(user)
            self.assert_error(self.end(assignment), 403, 'permission_denied')
        self.client.credentials()
        self.assert_error(self.end(assignment), 401, 'not_authenticated')
        self.login_as(self.president)
        self.assert_error(self.client.post(f'{ROLES}/999999/end'), 404, 'not_found')
        self.assertEqual(self.nominee.current_roles(), ['treasurer'])


class TwoPresidentsEndEachOtherTests(TransactionTestCase):
    """Two presidents end each other's terms at the same instant. Without
    the row locks both checks would see "one other president" and the club
    would be left with none.
    """

    serialized_rollback = True

    def test_exactly_one_is_refused(self):
        today = timezone.localdate()
        users = [
            User.objects.create_user(email=f'p{n}@example.com', name=f'P{n}', college_id=f'SSA-P{n}')
            for n in range(2)
        ]
        assignments = [
            RoleAssignment.objects.create(
                user=user, role='president', term_start=today - timedelta(days=30), term_end=today + timedelta(days=30),
            )
            for user in users
        ]
        barrier = threading.Barrier(2)
        outcomes = [None, None]

        def worker(index):
            try:
                barrier.wait(timeout=10)
                roles.end_role(assignment_id=assignments[1 - index].pk, actor=users[index])
                outcomes[index] = 'ended'
            except Exception as exc:
                outcomes[index] = exc
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertFalse(any(thread.is_alive() for thread in threads), 'an end_role thread hung')

        refused = [outcome for outcome in outcomes if isinstance(outcome, Exception)]
        self.assertEqual([type(exc) for exc in refused], [roles.LastPresident], outcomes)
        current = RoleAssignment.objects.filter(role='president', term_end__gte=today).count()
        self.assertEqual(current, 1)
