from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from common.testing import ApiTestCase
from events.tests.helpers import make_member
from members.models import Membership
from members.services import membership_status

User = get_user_model()
MEMBERS = '/api/members'


class MemberListTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.president = self.make_role_user('president')
        self.asha = self.make_user(email='asha.rao@example.com', name='Asha Rao', college_id='SSA-001')
        self.ravi = self.make_user(email='ravi@example.com', name='Ravi Menon', college_id='SSA-002')
        self.zoya = self.make_user(email='zoya@example.com', name='Zoya Khan', college_id='SSA-003')
        make_member(self.asha)                      # active
        make_member(self.ravi, days_left=-1)        # lapsed
        self.login_as(self.president)               # zoya and the president: none

    def names(self, **params):
        response = self.client.get(MEMBERS, params)
        self.assertEqual(response.status_code, 200, response.content)
        return [item['name'] for item in response.json()['results']]


class MemberListTests(MemberListTestCase):
    def test_lists_everyone_with_roles_and_membership_status(self):
        body = self.client.get(MEMBERS).json()

        self.assertEqual(body['count'], 4)
        self.assertEqual(set(body), {'count', 'next', 'previous', 'results'})
        by_name = {item['name']: item for item in body['results']}
        self.assertEqual(by_name['Asha Rao'], {
            'id': self.asha.id, 'email': 'asha.rao@example.com', 'name': 'Asha Rao',
            'college_id': 'SSA-001', 'roles': [], 'membership_status': 'active',
        })
        self.assertEqual(by_name['Ravi Menon']['membership_status'], 'lapsed')
        self.assertEqual(by_name['Zoya Khan']['membership_status'], 'none')
        self.assertEqual(by_name['President']['roles'], ['president'])

    def test_no_sensitive_fields_are_exposed(self):
        item = self.client.get(MEMBERS).json()['results'][0]
        self.assertEqual(set(item), {'id', 'email', 'name', 'college_id', 'roles', 'membership_status'})

    def test_status_matches_the_rule_used_everywhere_else(self):
        # Extra cases the list must agree on with /auth/me and check-in.
        make_member(self.zoya, days_left=0)                                   # last day: active
        cancelled = self.make_user(email='c@example.com', name='Cancelled Carl', college_id='SSA-C')
        Membership.objects.filter(pk=make_member(cancelled).pk).update(status='cancelled')
        renewed = self.make_user(email='r@example.com', name='Renewed Rita', college_id='SSA-RR')
        make_member(renewed, days_left=-40)
        make_member(renewed, days_left=300)

        listed = {item['id']: item['membership_status'] for item in self.client.get(MEMBERS).json()['results']}

        for user in User.objects.all():
            self.assertEqual(listed[user.id], membership_status(user), user.name)
        self.assertEqual(listed[cancelled.id], 'none')
        self.assertEqual(listed[renewed.id], 'active')

    def test_roles_are_current_terms_only_sorted_and_not_repeated(self):
        self.give_role(self.asha, 'treasurer')
        self.give_role(self.asha, 'treasurer', start_offset=-5, end_offset=5)       # overlapping duplicate
        self.give_role(self.asha, 'event_manager')
        self.give_role(self.asha, 'president', start_offset=-400, end_offset=-1)   # ended
        self.give_role(self.asha, 'volunteer_coordinator', start_offset=1, end_offset=30)   # not started

        by_name = {item['name']: item for item in self.client.get(MEMBERS).json()['results']}

        self.assertEqual(by_name['Asha Rao']['roles'], ['event_manager', 'treasurer'])
        self.assertEqual(by_name['Asha Rao']['roles'], self.asha.current_roles())

    def test_ordered_by_name(self):
        self.assertEqual(self.names(), ['Asha Rao', 'President', 'Ravi Menon', 'Zoya Khan'])

    def test_paginated_at_20(self):
        for number in range(20):
            self.make_user(email=f'extra{number}@example.com', name=f'Extra {number:02}', college_id=f'X{number}')

        first = self.client.get(MEMBERS).json()
        second = self.client.get(MEMBERS, {'page': 2}).json()

        self.assertEqual(first['count'], 24)
        self.assertEqual(len(first['results']), 20)
        self.assertIsNotNone(first['next'])
        self.assertEqual(len(second['results']), 4)
        self.assertEqual(len({item['id'] for item in first['results'] + second['results']}), 24)

    def test_list_is_read_only(self):
        self.assert_error(self.client.post(MEMBERS, {'name': 'New'}, format='json'), 405, 'method_not_allowed')


class MemberFilterTests(MemberListTestCase):
    def test_filter_by_each_membership_status(self):
        self.assertEqual(self.names(status='active'), ['Asha Rao'])
        self.assertEqual(self.names(status='lapsed'), ['Ravi Menon'])
        self.assertEqual(self.names(status='none'), ['President', 'Zoya Khan'])

    def test_filter_count_reflects_the_filter(self):
        self.assertEqual(self.client.get(MEMBERS, {'status': 'lapsed'}).json()['count'], 1)

    def test_unknown_status_is_a_400(self):
        for value in ['expired', 'ACTIVE', 'pending']:
            with self.subTest(value=value):
                response = self.client.get(MEMBERS, {'status': value})
                body = self.assert_error(response, 400, 'validation_error', field='status')
                self.assertEqual(self.field_codes(body), {('status', 'invalid_choice')})

    def test_search_matches_name_ignoring_case(self):
        self.assertEqual(self.names(search='asha'), ['Asha Rao'])
        self.assertEqual(self.names(search='MENON'), ['Ravi Menon'])
        self.assertEqual(self.names(search='Ra'), ['Asha Rao', 'Ravi Menon'])      # several matches

    def test_search_matches_email_ignoring_case(self):
        self.assertEqual(self.names(search='ZOYA@EXAMPLE'), ['Zoya Khan'])
        self.assertEqual(self.names(search='asha.rao@'), ['Asha Rao'])

    def test_search_does_not_match_other_fields(self):
        self.assertEqual(self.names(search='SSA-001'), [])        # college id is not searched

    def test_search_with_no_match_is_an_empty_page(self):
        body = self.client.get(MEMBERS, {'search': 'nobody-by-this-name'}).json()
        self.assertEqual((body['count'], body['results']), (0, []))

    def test_blank_search_is_ignored(self):
        self.assertEqual(len(self.names(search='   ')), 4)

    def test_wildcard_characters_are_matched_literally(self):
        self.assertEqual(self.names(search='%'), [])
        self.assertEqual(self.names(search='_'), [])

    def test_status_and_search_combine(self):
        self.assertEqual(self.names(status='active', search='ra'), ['Asha Rao'])    # Ravi matches the search but is lapsed
        self.assertEqual(self.names(status='lapsed', search='asha'), [])


class MemberListPermissionTests(MemberListTestCase):
    def test_president_treasurer_and_event_manager_may_read(self):
        for user in [self.president, self.make_role_user('treasurer'), self.make_role_user('event_manager')]:
            with self.subTest(user=user.email):
                self.login_as(user)
                self.assertEqual(self.client.get(MEMBERS).status_code, 200)

    def test_volunteer_coordinator_may_read_the_same_list(self):
        # They assign people to tasks, so they need the names.
        self.login_as(self.president)
        as_president = self.client.get(MEMBERS).json()
        coordinator = self.make_role_user('volunteer_coordinator')
        self.login_as(coordinator)

        response = self.client.get(MEMBERS)

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        # Same fields as every other reader gets, nothing more.
        self.assertEqual(set(body['results'][0]), {'id', 'email', 'name', 'college_id', 'roles', 'membership_status'})
        # Same people, plus the coordinator account created just above.
        self.assertEqual(body['count'], as_president['count'] + 1)
        listed = {item['id']: item for item in body['results']}
        for item in as_president['results']:
            self.assertEqual(listed[item['id']], item)
        self.assertEqual(listed[coordinator.id]['roles'], ['volunteer_coordinator'])

    def test_volunteer_coordinator_can_filter_and_search(self):
        self.login_as(self.make_role_user('volunteer_coordinator'))
        self.assertEqual(self.names(status='active'), ['Asha Rao'])
        self.assertEqual(self.names(search='menon'), ['Ravi Menon'])
        self.assert_error(self.client.get(MEMBERS, {'status': 'bogus'}), 400, 'validation_error', field='status')

    def test_list_stays_read_only_for_the_volunteer_coordinator(self):
        self.login_as(self.make_role_user('volunteer_coordinator'))
        before = User.objects.count()
        writes = [
            self.client.post(MEMBERS, {'name': 'New', 'email': 'new@example.com'}, format='json'),
            self.client.put(MEMBERS, {'name': 'New'}, format='json'),
            self.client.patch(MEMBERS, {'name': 'New'}, format='json'),
            self.client.delete(MEMBERS),
        ]
        for response in writes:
            self.assert_error(response, 405, 'method_not_allowed')
        # No per-member endpoint exists to edit or delete through either.
        for method in ['patch', 'put', 'delete']:
            response = getattr(self.client, method)(f'{MEMBERS}/{self.asha.id}', {'name': 'Hacked'}, format='json')
            self.assert_error(response, 404, 'not_found')
        self.asha.refresh_from_db()
        self.assertEqual((self.asha.name, User.objects.count()), ('Asha Rao', before))

    def test_coordinator_gains_no_other_staff_access(self):
        # Only the member list opened up; the money and admin endpoints did not.
        self.login_as(self.make_role_user('volunteer_coordinator'))
        for url in ['/api/finance/summary', '/api/audit', '/api/roles', '/api/expenses', '/api/health']:
            with self.subTest(url=url):
                self.assert_error(self.client.get(url), 403, 'permission_denied')

    def test_volunteer_coordinator_whose_term_ended_gets_403(self):
        former = self.make_user(email='oldvc@example.com', name='Old Coordinator', college_id='SSA-OVC')
        self.give_role(former, 'volunteer_coordinator', start_offset=-400, end_offset=-1)
        self.login_as(former)
        self.assert_error(self.client.get(MEMBERS), 403, 'permission_denied')

    def test_member_gets_403(self):
        self.login_as(self.asha)                    # an active, paid-up member with no role
        self.assert_error(self.client.get(MEMBERS), 403, 'permission_denied')

    def test_member_role_gets_403(self):
        # The "member" committee role is not a staff role.
        self.login_as(self.make_role_user('member'))
        self.assert_error(self.client.get(MEMBERS), 403, 'permission_denied')

    def test_filters_do_not_bypass_the_permission_check(self):
        self.login_as(self.asha)
        self.assert_error(self.client.get(MEMBERS, {'search': 'asha', 'status': 'active'}), 403, 'permission_denied')

    def test_treasurer_whose_term_has_ended_gets_403(self):
        former = self.make_user(email='former@example.com', name='Former', college_id='SSA-F')
        self.give_role(former, 'treasurer', start_offset=-400, end_offset=-1)
        self.login_as(former)
        self.assert_error(self.client.get(MEMBERS), 403, 'permission_denied')

    def test_not_logged_in_is_401(self):
        self.client.credentials()
        self.assert_error(self.client.get(MEMBERS), 401, 'not_authenticated')
