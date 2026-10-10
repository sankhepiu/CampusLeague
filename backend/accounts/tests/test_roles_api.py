from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import RoleAssignment
from audit.models import AuditLog
from common.testing import ApiTestCase

ROLES = '/api/roles'


class RolesApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        self.president = self.make_role_user('president')
        self.member = self.make_user()

    def body(self, **overrides):
        body = {
            'user': self.member.id, 'role': 'treasurer',
            'term_start': self.today.isoformat(),
            'term_end': (self.today + timedelta(days=365)).isoformat(),
        }
        body.update(overrides)
        return body

    # POST /roles used to grant the role at once. It now creates an invite
    # (maker-checker); the role exists only after the nominee accepts.
    # test_role_invites.py covers the invite itself.

    def test_president_nominates_and_the_role_takes_effect_only_on_acceptance(self):
        self.login_as(self.president)

        response = self.client.post(ROLES, self.body(), format='json')

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['status'], 'pending')
        self.assertEqual(self.member.current_roles(), [])
        self.assertEqual(RoleAssignment.objects.filter(user=self.member).count(), 0)

        self.login_as(self.member)
        accepted = self.client.post(f"{ROLES}/invites/{response.json()['id']}/accept")
        self.assertEqual(accepted.status_code, 200, accepted.content)
        self.assertEqual(self.member.current_roles(), ['treasurer'])

    def test_nomination_and_assignment_each_write_an_audit_row(self):
        self.login_as(self.president)
        invite_id = self.client.post(ROLES, self.body(), format='json').json()['id']

        log = AuditLog.objects.get()
        self.assertEqual((log.actor, log.action), (self.president, 'role.invited'))
        self.assertEqual((log.object_type, log.object_id), ('accounts.roleinvite', invite_id))
        self.assertEqual((log.after['role'], log.after['user']), ('treasurer', self.member.id))

        self.login_as(self.member)
        self.client.post(f'{ROLES}/invites/{invite_id}/accept')
        log = AuditLog.objects.get(action='role.assigned')
        assignment = RoleAssignment.objects.get(user=self.member)
        # The nominee is the actor: accepting is what created the role.
        self.assertEqual(log.actor, self.member)
        self.assertEqual((log.object_type, log.object_id), ('accounts.roleassignment', assignment.id))
        self.assertEqual(log.after['role'], 'treasurer')
        self.assertEqual(log.after['user'], self.member.id)
        self.assertEqual((log.after['invite'], log.after['invited_by']), (invite_id, self.president.id))

    def test_every_other_role_is_refused(self):
        for role in ['treasurer', 'event_manager', 'volunteer_coordinator', 'member']:
            with self.subTest(role=role):
                self.login_as(self.make_role_user(role))
                self.assert_error(self.client.post(ROLES, self.body(), format='json'), 403, 'permission_denied')
                self.assert_error(self.client.get(ROLES), 403, 'permission_denied')
        self.assertEqual(RoleAssignment.objects.filter(user=self.member).count(), 0)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_user_with_no_role_cannot_make_themselves_president(self):
        self.login_as(self.member)
        response = self.client.post(ROLES, self.body(role='president'), format='json')
        self.assert_error(response, 403, 'permission_denied')
        self.assertEqual(self.member.current_roles(), [])

    def test_not_logged_in_is_401(self):
        self.assert_error(self.client.post(ROLES, self.body(), format='json'), 401, 'not_authenticated')

    def test_president_whose_term_has_ended_is_refused(self):
        former = self.make_user(email='former@example.com', name='Former', college_id='SSA-old')
        self.give_role(former, 'president', start_offset=-400, end_offset=-1)
        self.login_as(former)
        self.assert_error(self.client.post(ROLES, self.body(), format='json'), 403, 'permission_denied')

    def test_president_whose_term_has_not_started_is_refused(self):
        elect = self.make_user(email='elect@example.com', name='Elect', college_id='SSA-new')
        self.give_role(elect, 'president', start_offset=1, end_offset=365)
        self.login_as(elect)
        self.assert_error(self.client.get(ROLES), 403, 'permission_denied')

    def test_invalid_input_is_refused_and_not_audited(self):
        self.login_as(self.president)
        cases = [
            (self.body(role='supreme_leader'), 'role', 'invalid_choice'),
            (self.body(user=999999), 'user', 'does_not_exist'),
            (self.body(term_start='not-a-date'), 'term_start', 'invalid'),
            (self.body(term_end=(self.today - timedelta(days=1)).isoformat()), 'term_end', 'term_end_before_start'),
        ]
        for body, field, code in cases:
            with self.subTest(field=field):
                response = self.client.post(ROLES, body, format='json')
                error = self.assert_error(response, 400, 'validation_error', field=field)
                self.assertIn((field, code), self.field_codes(error))
        self.assertEqual(RoleAssignment.objects.filter(user=self.member).count(), 0)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_president_lists_assignments(self):
        self.login_as(self.president)
        body = self.client.get(ROLES).json()
        self.assertEqual(body['count'], 1)
        self.assertEqual(body['results'][0]['role'], 'president')


class AuditLogAppendOnlyTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.login_as(self.make_role_user('president'))
        member = self.make_user()
        today = timezone.localdate()
        self.client.post(ROLES, {
            'user': member.id, 'role': 'treasurer',
            'term_start': today.isoformat(), 'term_end': today.isoformat(),
        }, format='json')

    def test_audit_row_cannot_be_updated(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            AuditLog.objects.update(action='nothing.happened')
        self.assertEqual(AuditLog.objects.get().action, 'role.invited')

    def test_audit_row_cannot_be_deleted(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            AuditLog.objects.all().delete()
        self.assertEqual(AuditLog.objects.count(), 1)
