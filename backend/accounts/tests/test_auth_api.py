from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.authtoken.models import Token

from accounts.models import RoleAssignment
from common.testing import PASSWORD, ApiTestCase

User = get_user_model()

SIGNUP = '/api/auth/signup'
LOGIN = '/api/auth/login'
LOGOUT = '/api/auth/logout'
ME = '/api/auth/me'


def signup_body(**overrides):
    body = {
        'email': 'priya@example.com',
        'password': PASSWORD,
        'name': 'Priya',
        'college_id': 'SSA-001',
        'phone': '+919876543210',
    }
    body.update(overrides)
    return body


class SignupTests(ApiTestCase):
    def test_signup_creates_an_unverified_user_and_returns_no_token(self):
        response = self.client.post(SIGNUP, signup_body(), format='json')

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json(), {'verification_required': True, 'email': 'priya@example.com'})
        user = User.objects.get()
        self.assertEqual((user.name, user.college_id, user.phone), ('Priya', 'SSA-001', '+919876543210'))
        self.assertFalse(user.email_verified)
        # No session exists until the email is verified.
        self.assertEqual(Token.objects.count(), 0)

    def test_password_is_hashed_and_never_returned(self):
        response = self.client.post(SIGNUP, signup_body(), format='json')

        user = User.objects.get()
        self.assertTrue(user.check_password(PASSWORD))
        self.assertNotIn(PASSWORD, user.password)
        self.assertNotIn(PASSWORD, response.content.decode())
        self.assertNotIn(user.password, response.content.decode())

    def test_signup_alone_gives_no_access(self):
        response = self.client.post(SIGNUP, signup_body(), format='json')
        self.assertNotIn('token', response.json())
        self.assert_error(self.client.get(ME), 401, 'not_authenticated')

    def test_phone_is_optional(self):
        body = signup_body()
        del body['phone']
        response = self.client.post(SIGNUP, body, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(User.objects.get().phone, '')

    def test_email_is_normalised_to_lowercase(self):
        response = self.client.post(SIGNUP, signup_body(email='Priya@Example.COM'), format='json')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(User.objects.get().email, 'priya@example.com')

    def test_privilege_fields_from_the_client_are_ignored(self):
        body = signup_body(is_staff=True, is_superuser=True, roles=['president'], id=999, email_verified=True)
        response = self.client.post(SIGNUP, body, format='json')

        self.assertEqual(response.status_code, 201, response.content)
        user = User.objects.get()
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertNotEqual(user.id, 999)
        self.assertEqual(RoleAssignment.objects.count(), 0)
        self.assertEqual(User.objects.get().current_roles(), [])
        self.assertFalse(User.objects.get().email_verified)       # nor can the client mark itself verified

    def test_duplicate_email_is_rejected(self):
        self.make_user()
        response = self.client.post(SIGNUP, signup_body(name='Impostor'), format='json')

        body = self.assert_error(response, 400, 'validation_error', field='email')
        self.assertEqual(self.field_codes(body), {('email', 'email_taken')})
        self.assertEqual(User.objects.count(), 1)

    def test_duplicate_email_differing_only_by_case_is_rejected(self):
        self.make_user()
        response = self.client.post(SIGNUP, signup_body(email='PRIYA@example.com'), format='json')

        body = self.assert_error(response, 400, 'validation_error', field='email')
        self.assertEqual(self.field_codes(body), {('email', 'email_taken')})
        self.assertEqual(User.objects.count(), 1)

    def test_empty_body_reports_every_required_field(self):
        response = self.client.post(SIGNUP, {}, format='json')

        body = self.assert_error(response, 400, 'validation_error', field='email')
        self.assertEqual(self.field_codes(body), {
            ('email', 'required'),
            ('password', 'required'),
            ('name', 'required'),
            ('college_id', 'required'),
        })
        self.assertEqual(User.objects.count(), 0)

    def test_blank_values_are_rejected(self):
        response = self.client.post(
            SIGNUP, signup_body(name='   ', college_id=''), format='json',
        )
        body = self.assert_error(response, 400, 'validation_error', field='name')
        self.assertEqual(self.field_codes(body), {('name', 'blank'), ('college_id', 'blank')})
        self.assertEqual(User.objects.count(), 0)

    def test_invalid_email_is_rejected(self):
        response = self.client.post(SIGNUP, signup_body(email='not-an-email'), format='json')
        body = self.assert_error(response, 400, 'validation_error', field='email')
        self.assertEqual(self.field_codes(body), {('email', 'invalid')})

    def test_wrong_type_is_rejected(self):
        response = self.client.post(SIGNUP, signup_body(name=['a', 'list']), format='json')
        body = self.assert_error(response, 400, 'validation_error', field='name')
        self.assertEqual(self.field_codes(body), {('name', 'invalid')})

    def test_overlong_values_are_rejected(self):
        response = self.client.post(
            SIGNUP, signup_body(name='x' * 151, college_id='y' * 51), format='json',
        )
        body = self.assert_error(response, 400, 'validation_error', field='name')
        # college_id is now capped at 20 and must match the id format.
        self.assertEqual(self.field_codes(body), {
            ('name', 'max_length'), ('college_id', 'max_length'), ('college_id', 'invalid_college_id'),
        })

    def test_name_at_maximum_length_is_accepted(self):
        response = self.client.post(SIGNUP, signup_body(name='x' * 150), format='json')
        self.assertEqual(response.status_code, 201, response.content)

    def test_invalid_phone_is_rejected(self):
        for phone in ['12345', 'call-me-maybe', '+91 98765 43210', '1' * 16]:
            with self.subTest(phone=phone):
                response = self.client.post(SIGNUP, signup_body(phone=phone), format='json')
                self.assert_error(response, 400, 'validation_error', field='phone')
        self.assertEqual(User.objects.count(), 0)

    def test_weak_passwords_are_rejected(self):
        cases = {
            'short1A': 'password_too_short',
            'password': 'password_too_common',
            '8274619350': 'password_entirely_numeric',
            'priya@example.com': 'password_too_similar',
        }
        for password, code in cases.items():
            with self.subTest(password=password):
                response = self.client.post(SIGNUP, signup_body(password=password), format='json')
                body = self.assert_error(response, 400, 'validation_error', field='password')
                self.assertIn(('password', code), self.field_codes(body))
        self.assertEqual(User.objects.count(), 0)

    def test_malformed_json_is_a_clean_400(self):
        response = self.client.post(SIGNUP, '{"email": ', content_type='application/json')
        self.assert_error(response, 400, 'parse_error')

    def test_form_encoded_body_is_refused(self):
        response = self.client.post(SIGNUP, signup_body())  # multipart, not JSON
        self.assert_error(response, 415, 'unsupported_media_type')
        self.assertEqual(User.objects.count(), 0)

    def test_get_is_not_allowed(self):
        self.assert_error(self.client.get(SIGNUP), 405, 'method_not_allowed')

    def test_stale_authorization_header_does_not_block_signup(self):
        self.use_token('not-a-real-token')
        response = self.client.post(SIGNUP, signup_body(), format='json')
        self.assertEqual(response.status_code, 201, response.content)


class LoginTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()

    def login(self, email='priya@example.com', password=PASSWORD):
        return self.client.post(LOGIN, {'email': email, 'password': password}, format='json')

    def test_login_returns_token_and_user(self):
        response = self.login()

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body['token'], Token.objects.get(user=self.user).key)
        self.assertEqual(body['user']['email'], 'priya@example.com')
        self.assertNotIn('password', body['user'])

    def test_email_is_case_insensitive(self):
        self.assertEqual(self.login(email='PRIYA@Example.com').status_code, 200)

    def test_second_login_returns_the_same_token(self):
        first = self.login().json()['token']
        second = self.login().json()['token']
        self.assertEqual(first, second)
        self.assertEqual(Token.objects.count(), 1)

    def test_wrong_password_is_rejected(self):
        response = self.login(password='wrong-password')
        self.assert_error(response, 401, 'invalid_credentials')
        self.assertEqual(response['WWW-Authenticate'], 'Token')
        self.assertEqual(Token.objects.count(), 0)

    def test_unknown_email_looks_identical_to_wrong_password(self):
        wrong_password = self.login(password='wrong-password')
        unknown_email = self.login(email='nobody@example.com')

        self.assert_error(unknown_email, 401, 'invalid_credentials')
        self.assertEqual(unknown_email.json(), wrong_password.json())

    def test_inactive_user_cannot_log_in(self):
        self.user.is_active = False
        self.user.save()
        self.assert_error(self.login(), 401, 'invalid_credentials')
        self.assertEqual(Token.objects.count(), 0)

    def test_missing_fields_are_a_400_not_a_401(self):
        response = self.client.post(LOGIN, {}, format='json')
        body = self.assert_error(response, 400, 'validation_error', field='email')
        self.assertEqual(self.field_codes(body), {('email', 'required'), ('password', 'required')})

    def test_stale_authorization_header_does_not_block_login(self):
        self.use_token('not-a-real-token')
        self.assertEqual(self.login().status_code, 200)


class LogoutTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.token = Token.objects.create(user=self.user)

    def test_logout_requires_a_token(self):
        self.assert_error(self.client.post(LOGOUT), 401, 'not_authenticated')
        self.assertEqual(Token.objects.count(), 1)

    def test_logout_deletes_the_token(self):
        self.use_token(self.token.key)

        response = self.client.post(LOGOUT)

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b'')
        self.assertEqual(Token.objects.count(), 0)

    def test_token_no_longer_works_after_logout(self):
        self.use_token(self.token.key)
        self.client.post(LOGOUT)
        self.assert_error(self.client.get(ME), 401, 'authentication_failed')

    def test_logout_only_ends_the_callers_session(self):
        other = self.make_user(email='ravi@example.com', name='Ravi', college_id='SSA-002')
        other_token = Token.objects.create(user=other)
        self.use_token(self.token.key)

        self.client.post(LOGOUT)

        self.assertTrue(Token.objects.filter(pk=other_token.pk).exists())


class MeTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user(phone='+919876543210')
        self.token = Token.objects.create(user=self.user)
        self.today = timezone.localdate()

    def test_requires_a_token(self):
        response = self.client.get(ME)
        self.assert_error(response, 401, 'not_authenticated')
        self.assertEqual(response['WWW-Authenticate'], 'Token')

    def test_unknown_token_is_rejected(self):
        self.use_token('0' * 40)
        self.assert_error(self.client.get(ME), 401, 'authentication_failed')

    def test_wrong_scheme_is_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token.key}')
        self.assert_error(self.client.get(ME), 401, 'not_authenticated')

    def test_inactive_user_token_is_rejected(self):
        self.user.is_active = False
        self.user.save()
        self.use_token(self.token.key)
        self.assert_error(self.client.get(ME), 401, 'authentication_failed')

    def test_returns_the_token_owner(self):
        self.use_token(self.token.key)

        response = self.client.get(ME)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), {
            'id': self.user.id,
            'email': 'priya@example.com',
            'name': 'Priya',
            'college_id': 'SSA-001',
            'phone': '+919876543210',
            'roles': [],
            'membership_status': 'none',
        })

    def test_user_id_in_the_query_string_is_ignored(self):
        other = self.make_user(email='ravi@example.com', name='Ravi', college_id='SSA-002')
        self.use_token(self.token.key)

        response = self.client.get(ME, {'id': other.id, 'user_id': other.id})

        self.assertEqual(response.json()['id'], self.user.id)

    def test_roles_are_only_those_whose_term_includes_today(self):
        day = timedelta(days=1)
        terms = [
            ('treasurer', self.today - 30 * day, self.today + 30 * day),   # current
            ('event_manager', self.today, self.today),                      # current, one day
            ('president', self.today - 400 * day, self.today - day),        # ended yesterday
            ('volunteer_coordinator', self.today + day, self.today + 30 * day),  # starts tomorrow
        ]
        for role, start, end in terms:
            RoleAssignment.objects.create(user=self.user, role=role, term_start=start, term_end=end)
        self.use_token(self.token.key)

        response = self.client.get(ME)

        self.assertEqual(response.json()['roles'], ['event_manager', 'treasurer'])

    def test_another_users_roles_are_not_shown(self):
        other = self.make_user(email='ravi@example.com', name='Ravi', college_id='SSA-002')
        RoleAssignment.objects.create(
            user=other, role='president', term_start=self.today, term_end=self.today,
        )
        self.use_token(self.token.key)

        self.assertEqual(self.client.get(ME).json()['roles'], [])

    def test_post_is_not_allowed(self):
        self.use_token(self.token.key)
        self.assert_error(self.client.post(ME, {}, format='json'), 405, 'method_not_allowed')
