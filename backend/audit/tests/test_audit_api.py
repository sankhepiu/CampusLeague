from datetime import timedelta

from django.utils import timezone

from audit.models import AuditLog
from common.testing import ApiTestCase

AUDIT = '/api/audit'


class AuditApiTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.president = self.make_role_user('president')
        self.member = self.make_user()
        now = timezone.now()
        self.oldest = AuditLog.objects.create(
            actor=self.president, action='role.assigned', object_type='accounts.roleassignment', object_id=7,
            after={'role': 'treasurer'}, at=now - timedelta(hours=2),
        )
        self.middle = AuditLog.objects.create(
            actor=self.member, action='stock.restocked', object_type='shop.productsize', object_id=3,
            before={'stock': 5}, after={'stock': 12, 'added': 7}, at=now - timedelta(hours=1),
        )
        self.newest = AuditLog.objects.create(
            actor=None, action='role.assigned', object_type='accounts.roleassignment', object_id=8, at=now,
        )
        self.login_as(self.president)


class AuditListTests(AuditApiTestCase):
    def test_lists_newest_first_in_the_agreed_shape(self):
        body = self.client.get(AUDIT).json()

        self.assertEqual(set(body), {'count', 'next', 'previous', 'results'})
        self.assertEqual([item['id'] for item in body['results']], [self.newest.id, self.middle.id, self.oldest.id])
        item = body['results'][1]
        self.assertEqual(set(item), {'id', 'actor', 'action', 'object_type', 'object_id', 'before', 'after', 'at'})
        self.assertEqual(item['actor'], {'id': self.member.id, 'name': 'Priya'})
        self.assertEqual((item['action'], item['object_type'], item['object_id']), ('stock.restocked', 'shop.productsize', 3))
        self.assertEqual((item['before'], item['after']), ({'stock': 5}, {'stock': 12, 'added': 7}))
        self.assertTrue(item['at'])

    def test_row_without_an_actor_has_actor_null(self):
        newest = self.client.get(AUDIT).json()['results'][0]
        self.assertIsNone(newest['actor'])
        self.assertEqual((newest['before'], newest['after']), (None, None))

    def test_action_filter(self):
        body = self.client.get(AUDIT, {'action': 'role.assigned'}).json()
        self.assertEqual(body['count'], 2)
        self.assertEqual([item['id'] for item in body['results']], [self.newest.id, self.oldest.id])
        self.assertEqual(self.client.get(AUDIT, {'action': 'stock.restocked'}).json()['count'], 1)

    def test_action_filter_is_an_exact_match(self):
        for value in ['role', 'ROLE.ASSIGNED', 'role.assigned ', 'nothing.like.this']:
            with self.subTest(value=value):
                self.assertEqual(self.client.get(AUDIT, {'action': value}).json()['count'], 0)

    def test_blank_filter_is_ignored(self):
        self.assertEqual(self.client.get(AUDIT, {'action': ''}).json()['count'], 3)

    def test_paginated_at_20(self):
        for number in range(20):
            AuditLog.objects.create(action='bulk.row', object_type='x', object_id=number)
        first = self.client.get(AUDIT).json()
        self.assertEqual((first['count'], len(first['results'])), (23, 20))
        self.assertEqual(len(self.client.get(AUDIT, {'page': 2}).json()['results']), 3)

    def test_real_actions_show_up(self):
        # A row written by the application itself, not by this test.
        today = timezone.localdate().isoformat()
        self.client.post('/api/roles', {'user': self.member.id, 'role': 'treasurer', 'term_start': today, 'term_end': today}, format='json')
        newest = self.client.get(AUDIT).json()['results'][0]
        self.assertEqual((newest['action'], newest['actor']['id'], newest['after']['role']), ('role.invited', self.president.id, 'treasurer'))

    def test_log_is_read_only_through_the_api(self):
        self.assert_error(self.client.post(AUDIT, {'action': 'forged'}, format='json'), 405, 'method_not_allowed')
        self.assert_error(self.client.delete(AUDIT), 405, 'method_not_allowed')
        self.assert_error(self.client.delete(f'{AUDIT}/{self.oldest.id}'), 404, 'not_found')
        self.assertEqual(AuditLog.objects.count(), 3)


class AuditPermissionTests(AuditApiTestCase):
    def test_only_the_president_may_read_it(self):
        refused = [self.make_role_user(role) for role in ['treasurer', 'event_manager', 'volunteer_coordinator', 'member']]
        refused.append(self.member)
        for user in refused:
            with self.subTest(user=user.email):
                self.login_as(user)
                self.assert_error(self.client.get(AUDIT), 403, 'permission_denied')
                self.assert_error(self.client.get(AUDIT, {'action': 'role.assigned'}), 403, 'permission_denied')
        self.client.credentials()
        self.assert_error(self.client.get(AUDIT), 401, 'not_authenticated')

    def test_former_president_is_refused(self):
        former = self.make_user(email='former@example.com', name='Former', college_id='SSA-F')
        self.give_role(former, 'president', start_offset=-400, end_offset=-1)
        self.login_as(former)
        self.assert_error(self.client.get(AUDIT), 403, 'permission_denied')
