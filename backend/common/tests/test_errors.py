from unittest import mock

from django.test import override_settings
from django.urls import path
from rest_framework.permissions import AllowAny
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from common.testing import PASSWORD, ApiTestCase

SECRET_DETAIL = 'db-password-hunter2'


class ExplodingView(APIView):
    """Stands in for a bug: an exception no endpoint anticipated."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        raise RuntimeError(f'boom {SECRET_DETAIL}')


# Used as the URLconf by UnhandledErrorTests only.
urlpatterns = [path('api/explode', ExplodingView.as_view())]


class UnknownPathTests(ApiTestCase):
    def test_unknown_api_path_is_a_json_404(self):
        self.assert_error(self.client.get('/api/nope'), 404, 'not_found')

    def test_nested_unknown_path_is_a_json_404(self):
        self.assert_error(self.client.get('/api/auth/nope/deeper'), 404, 'not_found')

    def test_trailing_slash_is_a_json_404_not_a_redirect(self):
        self.assert_error(self.client.get('/api/auth/me/'), 404, 'not_found')

    def test_every_method_gets_the_same_404(self):
        for method in ['post', 'put', 'patch', 'delete']:
            with self.subTest(method=method):
                response = getattr(self.client, method)('/api/nope', {}, format='json')
                self.assert_error(response, 404, 'not_found')

    def test_404_does_not_require_or_check_a_token(self):
        self.use_token('not-a-real-token')
        self.assert_error(self.client.get('/api/nope'), 404, 'not_found')

    @override_settings(DEBUG=True)
    def test_debug_mode_does_not_list_url_patterns(self):
        response = self.client.get('/api/nope')
        body = self.assert_error(response, 404, 'not_found')
        self.assertEqual(set(body), {'code', 'message', 'field'})
        self.assertNotIn('auth/signup', response.content.decode())


@override_settings(ROOT_URLCONF='common.tests.test_errors')
class UnhandledErrorTests(ApiTestCase):
    def assert_safe_500(self):
        with self.assertLogs('campusleague.api', level='ERROR') as logs:
            response = self.client.get('/api/explode')

        body = self.assert_error(response, 500, 'server_error')
        self.assertEqual(set(body), {'code', 'message', 'field'})
        text = response.content.decode()
        for leak in [SECRET_DETAIL, 'RuntimeError', 'Traceback', 'boom']:
            self.assertNotIn(leak, text)
        # The detail is not lost: it is in the server log for debugging.
        self.assertIn(SECRET_DETAIL, logs.output[0])
        self.assertIn('RuntimeError', logs.output[0])

    def test_unhandled_error_is_a_generic_json_500(self):
        self.assert_safe_500()

    @override_settings(DEBUG=True)
    def test_no_traceback_even_with_debug_on(self):
        self.assert_safe_500()


class ThrottleTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        # Pin the rates: they are configurable through the environment, and
        # these tests must not depend on a developer's .env.
        patcher = mock.patch.object(
            SimpleRateThrottle, 'THROTTLE_RATES', {'login': '20/min', 'signup': '10/min'},
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_login_is_throttled_after_20_attempts_a_minute(self):
        self.make_user()
        body = {'email': 'priya@example.com', 'password': 'wrong-password'}

        for attempt in range(20):
            response = self.client.post('/api/auth/login', body, format='json')
            self.assertEqual(response.status_code, 401, f'attempt {attempt + 1}')

        response = self.client.post('/api/auth/login', body, format='json')
        self.assert_error(response, 429, 'throttled')
        self.assertGreater(int(response['Retry-After']), 0)

    def test_throttled_login_refuses_even_the_correct_password(self):
        self.make_user()
        for _ in range(20):
            self.client.post(
                '/api/auth/login',
                {'email': 'priya@example.com', 'password': 'wrong-password'}, format='json',
            )

        response = self.client.post(
            '/api/auth/login', {'email': 'priya@example.com', 'password': PASSWORD}, format='json',
        )
        self.assert_error(response, 429, 'throttled')

    def test_signup_is_throttled_after_10_attempts_a_minute(self):
        for attempt in range(10):
            response = self.client.post('/api/auth/signup', {}, format='json')
            self.assertEqual(response.status_code, 400, f'attempt {attempt + 1}')

        self.assert_error(self.client.post('/api/auth/signup', {}, format='json'), 429, 'throttled')

    def test_login_and_signup_limits_are_counted_separately(self):
        for _ in range(10):
            self.client.post('/api/auth/signup', {}, format='json')

        response = self.client.post('/api/auth/login', {}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_other_endpoints_are_not_throttled(self):
        self.login_as(self.make_user())
        for _ in range(30):
            self.assertEqual(self.client.get('/api/auth/me').status_code, 200)
