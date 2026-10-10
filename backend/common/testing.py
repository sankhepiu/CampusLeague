from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

User = get_user_model()

PASSWORD = 'correct-horse-battery'


class ApiTestCase(APITestCase):
    """Shared helpers for API tests."""

    def setUp(self):
        super().setUp()
        # Throttle counters live in the cache; without this, requests made by
        # one test would count against the next.
        cache.clear()

    def make_user(self, email='priya@example.com', **extra):
        fields = {'password': PASSWORD, 'name': 'Priya', 'college_id': 'SSA-001'}
        fields.update(extra)
        return User.objects.create_user(email=email, **fields)

    def use_token(self, key):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {key}')

    def login_as(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.use_token(token.key)

    def assert_error(self, response, status, code, field=None):
        self.assertEqual(response.status_code, status, response.content)
        self.assertEqual(response['Content-Type'], 'application/json')
        body = response.json()
        self.assertGreaterEqual(set(body), {'code', 'message', 'field'})
        self.assertEqual(body['code'], code)
        self.assertEqual(body['field'], field)
        self.assertTrue(body['message'])
        return body

    def field_codes(self, body):
        return {(error['field'], error['code']) for error in body['errors']}

    def give_role(self, user, role, start_offset=-30, end_offset=30):
        """Assign a role whose term runs from today+start_offset to
        today+end_offset days (so the default is a current term)."""
        from datetime import timedelta

        from django.utils import timezone

        from accounts.models import RoleAssignment

        today = timezone.localdate()
        return RoleAssignment.objects.create(
            user=user, role=role,
            term_start=today + timedelta(days=start_offset),
            term_end=today + timedelta(days=end_offset),
        )

    def make_role_user(self, role, **term):
        user = self.make_user(email=f'{role}@example.com', name=role.title(), college_id=f'SSA-{role}')
        self.give_role(user, role, **term)
        return user
