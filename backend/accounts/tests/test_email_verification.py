import re
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.utils import timezone
from rest_framework.authtoken.models import Token

from accounts import verification
from accounts.models import EmailVerificationCode
from common.testing import PASSWORD, ApiTestCase

User = get_user_model()

SIGNUP, VERIFY, RESEND, LOGIN, ME = (
    '/api/auth/signup', '/api/auth/verify-email', '/api/auth/resend-code', '/api/auth/login', '/api/auth/me',
)
EMAIL = 'priya@example.com'


class VerificationTestCase(ApiTestCase):
    def signup(self, email=EMAIL):
        response = self.client.post(SIGNUP, {
            'email': email, 'password': PASSWORD, 'name': 'Priya', 'college_id': 'SSA-041',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        return response

    def emailed_code(self, index=-1):
        """The code as the user would read it in their inbox."""
        return re.search(r'\b(\d{6})\b', mail.outbox[index].body).group(1)

    def wrong_code(self):
        return '000000' if self.emailed_code() != '000000' else '111111'

    def verify(self, code, email=EMAIL):
        return self.client.post(VERIFY, {'email': email, 'code': code}, format='json')

    def login(self, password=PASSWORD, email=EMAIL):
        return self.client.post(LOGIN, {'email': email, 'password': password}, format='json')

    def record(self):
        return EmailVerificationCode.objects.get(user__email=EMAIL)

    def age_code(self, **delta):
        """Move the stored code into the past, as if time had gone by."""
        record = self.record()
        EmailVerificationCode.objects.filter(pk=record.pk).update(
            sent_at=record.sent_at - timedelta(**delta), expires_at=record.expires_at - timedelta(**delta),
        )


class SignupVerifyLoginFlowTests(VerificationTestCase):
    def test_full_flow_signup_verify_login(self):
        # 1. Sign up: no token, a code is emailed.
        response = self.signup()
        self.assertEqual(response.json(), {'verification_required': True, 'email': EMAIL})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [EMAIL])
        code = self.emailed_code()

        # 2. Not verified yet: login is refused even with the right password.
        self.assert_error(self.login(), 403, 'email_not_verified')

        # 3. Verify: the response is a login.
        verified = self.verify(code)
        self.assertEqual(verified.status_code, 200, verified.content)
        user = User.objects.get()
        self.assertTrue(user.email_verified)
        self.assertEqual(verified.json(), {
            'token': Token.objects.get(user=user).key,
            'user': {
                'id': user.id, 'email': EMAIL, 'name': 'Priya', 'college_id': 'SSA-041', 'phone': '',
                'roles': [], 'membership_status': 'none',
            },
        })

        # 4. The token works, and so does logging in normally from now on.
        self.use_token(verified.json()['token'])
        self.assertEqual(self.client.get(ME).status_code, 200)
        self.client.credentials()
        login = self.login()
        self.assertEqual(login.status_code, 200, login.content)

    def test_verify_response_has_exactly_the_login_shape(self):
        self.signup()
        verified = self.verify(self.emailed_code()).json()
        login = self.login().json()
        self.assertEqual(verified, login)
        self.assertEqual(set(verified), {'token', 'user'})

    def test_email_is_matched_ignoring_case_and_spaces(self):
        self.signup()
        self.assertEqual(self.verify(self.emailed_code(), email='  PRIYA@Example.com ').status_code, 200)

    def test_code_email_contents(self):
        self.signup()
        message = mail.outbox[0]
        self.assertEqual(message.subject, 'Your Campus League verification code')
        self.assertRegex(message.body, r'verification code is \d{6}\b')
        self.assertIn('10 minutes', message.body)
        self.assertNotIn(PASSWORD, message.body)

    def test_signup_still_succeeds_when_the_email_cannot_be_sent(self):
        with mock.patch('accounts.verification.send_mail', side_effect=ConnectionRefusedError('smtp down')):
            with self.assertLogs('campusleague.verification', level='ERROR'):
                response = self.client.post(SIGNUP, {
                    'email': EMAIL, 'password': PASSWORD, 'name': 'Priya', 'college_id': 'SSA-041',
                }, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(User.objects.filter(email=EMAIL).exists())
        # ...and a later resend delivers a working code.
        self.age_code(seconds=61)
        self.client.post(RESEND, {'email': EMAIL}, format='json')
        self.assertEqual(self.verify(self.emailed_code()).status_code, 200)


class WrongExpiredAndReusedCodeTests(VerificationTestCase):
    def setUp(self):
        super().setUp()
        self.signup()
        self.code = self.emailed_code()

    def assert_still_unverified(self):
        self.assertFalse(User.objects.get().email_verified)
        self.assertEqual(Token.objects.count(), 0)

    def test_wrong_code(self):
        self.assert_error(self.verify(self.wrong_code()), 400, 'invalid_code')
        self.assert_still_unverified()
        self.assertEqual(self.record().attempts, 1)

    def test_malformed_codes_are_just_wrong_codes(self):
        # Four, to stay under the five-attempt lockout.
        for code in ['12345', 'abcdef', self.code + '0', '-' + self.code]:
            with self.subTest(code=code):
                self.assert_error(self.verify(code), 400, 'invalid_code')
        self.assertEqual(self.record().attempts, 4)
        self.assert_still_unverified()

    def test_blank_code_is_a_validation_error_and_not_counted(self):
        self.assert_error(self.verify(' '), 400, 'validation_error', field='code')
        self.assertEqual(self.record().attempts, 0)

    def test_right_code_after_wrong_ones_still_works(self):
        for _ in range(4):
            self.assert_error(self.verify(self.wrong_code()), 400, 'invalid_code')
        self.assertEqual(self.verify(self.code).status_code, 200)

    def test_expired_code(self):
        self.age_code(minutes=10, seconds=1)
        self.assert_error(self.verify(self.code), 400, 'code_expired')
        self.assert_still_unverified()

    def test_code_is_valid_just_before_ten_minutes(self):
        self.age_code(minutes=9, seconds=50)
        self.assertEqual(self.verify(self.code).status_code, 200)

    def test_reused_code_is_refused(self):
        first = self.verify(self.code)
        self.assertEqual(first.status_code, 200)

        again = self.verify(self.code)

        self.assert_error(again, 400, 'invalid_code')
        self.assertEqual(Token.objects.count(), 1)
        self.assertFalse(EmailVerificationCode.objects.exists())      # single use: the code is gone

    def test_one_users_code_does_not_verify_another_user(self):
        # Fixed codes, so the two are certainly different.
        with mock.patch('accounts.verification.new_code', return_value='246810'):
            self.signup(email='ravi@example.com')
        with mock.patch('accounts.verification.new_code', return_value='135791'):
            self.age_code(seconds=61)
            self.client.post(RESEND, {'email': EMAIL}, format='json')

        response = self.verify('246810', email=EMAIL)                   # Ravi's code, Priya's email

        self.assert_error(response, 400, 'invalid_code')
        self.assertFalse(User.objects.get(email=EMAIL).email_verified)
        self.assertEqual(self.verify('246810', email='ravi@example.com').status_code, 200)

    def test_unknown_email_looks_like_a_wrong_code(self):
        self.assert_error(self.verify(self.code, email='nobody@example.com'), 400, 'invalid_code')

    def test_already_verified_account_looks_like_a_wrong_code(self):
        verified = self.make_user(email='old@example.com', name='Old', college_id='SSA-O')
        self.assert_error(self.verify('123456', email=verified.email), 400, 'invalid_code')

    def test_missing_fields_are_validation_errors(self):
        response = self.client.post(VERIFY, {}, format='json')
        body = self.assert_error(response, 400, 'validation_error', field='email')
        self.assertEqual(self.field_codes(body), {('email', 'required'), ('code', 'required')})


class LockoutTests(VerificationTestCase):
    def setUp(self):
        super().setUp()
        self.signup()
        self.code = self.emailed_code()

    def test_fifth_wrong_attempt_voids_the_code(self):
        for attempt in range(1, 5):
            self.assert_error(self.verify(self.wrong_code()), 400, 'invalid_code')
            self.assertEqual(self.record().attempts, attempt)

        fifth = self.verify(self.wrong_code())
        self.assert_error(fifth, 429, 'too_many_attempts')

        # Even the right code is refused now.
        self.assert_error(self.verify(self.code), 429, 'too_many_attempts')
        self.assertFalse(User.objects.get().email_verified)
        self.assertEqual(Token.objects.count(), 0)

    def test_attempts_do_not_keep_counting_after_lockout(self):
        for _ in range(8):
            self.verify(self.wrong_code())
        self.assertEqual(self.record().attempts, verification.MAX_ATTEMPTS)

    def test_a_new_code_after_lockout_works(self):
        for _ in range(5):
            self.verify(self.wrong_code())
        self.age_code(seconds=61)

        self.assertEqual(self.client.post(RESEND, {'email': EMAIL}, format='json').json(), {'sent': True})
        new_code = self.emailed_code()

        self.assertEqual(self.record().attempts, 0)
        self.assertEqual(self.verify(new_code).status_code, 200)

    def test_lockout_is_per_account(self):
        self.signup(email='ravi@example.com')
        ravi_code = self.emailed_code()
        for _ in range(5):
            self.verify(self.wrong_code())                  # locks Priya
        self.assertEqual(self.verify(ravi_code, email='ravi@example.com').status_code, 200)


class ResendTests(VerificationTestCase):
    def resend(self, email=EMAIL):
        return self.client.post(RESEND, {'email': email}, format='json')

    def test_resend_voids_the_old_code_and_the_new_one_works(self):
        # Fixed codes, so the old and new ones are certainly different.
        with mock.patch('accounts.verification.new_code', side_effect=['111111', '222222']):
            self.signup()
            self.age_code(seconds=61)
            response = self.resend()

        self.assertEqual((response.status_code, response.json()), (200, {'sent': True}))
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual((self.emailed_code(0), self.emailed_code(1)), ('111111', '222222'))
        self.assert_error(self.verify('111111'), 400, 'invalid_code')       # the old code is void
        self.assertEqual(self.verify('222222').status_code, 200)

    def test_new_code_gets_a_fresh_ten_minutes(self):
        self.signup()
        self.age_code(minutes=9)
        self.resend()
        remaining = self.record().expires_at - timezone.now()
        self.assertGreater(remaining, timedelta(minutes=9, seconds=50))

    def test_at_most_one_email_per_60_seconds_but_the_answer_is_the_same(self):
        self.signup()                                        # email 1
        first = self.resend()                                # within 60s of signup: not sent
        self.assertEqual(len(mail.outbox), 1)
        self.age_code(seconds=59)
        second = self.resend()                               # 59s: still not sent
        self.assertEqual(len(mail.outbox), 1)
        self.age_code(seconds=2)
        third = self.resend()                                # 61s: sent
        self.assertEqual(len(mail.outbox), 2)
        fourth = self.resend()                               # immediately again: not sent
        self.assertEqual(len(mail.outbox), 2)
        for response in [first, second, third, fourth]:
            self.assertEqual((response.status_code, response.json()), (200, {'sent': True}))

    def test_code_is_unchanged_when_a_resend_is_skipped(self):
        self.signup()
        code = self.emailed_code()
        self.resend()
        self.assertEqual(self.verify(code).status_code, 200)

    def test_response_is_identical_for_unknown_verified_and_unverified_emails(self):
        self.signup()
        self.age_code(seconds=61)
        self.make_user(email='verified@example.com', name='V', college_id='SSA-V')
        mail.outbox.clear()

        unverified = self.resend(EMAIL)
        unknown = self.resend('nobody@example.com')
        verified = self.resend('verified@example.com')
        garbage = self.resend('not-an-email')

        for response in [unverified, unknown, verified, garbage]:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, unverified.content)
            self.assertEqual(response.headers.get('Content-Type'), unverified.headers.get('Content-Type'))
        self.assertEqual(unverified.json(), {'sent': True})
        # Only the real, unverified account was actually emailed.
        self.assertEqual([message.to for message in mail.outbox], [[EMAIL]])
        self.assertEqual(EmailVerificationCode.objects.count(), 1)

    def test_verified_account_is_never_sent_a_code(self):
        self.make_user(email='verified@example.com', name='V', college_id='SSA-V')
        self.resend('verified@example.com')
        self.assertEqual(mail.outbox, [])

    def test_missing_email_is_a_validation_error(self):
        self.assert_error(self.client.post(RESEND, {}, format='json'), 400, 'validation_error', field='email')


class UnverifiedLoginTests(VerificationTestCase):
    def setUp(self):
        super().setUp()
        self.signup()

    def test_unverified_login_is_blocked_with_its_own_code(self):
        response = self.login()
        self.assert_error(response, 403, 'email_not_verified')
        self.assertEqual(Token.objects.count(), 0)

    def test_wrong_password_on_an_unverified_account_reveals_nothing(self):
        unverified = self.login(password='wrong-password')
        unknown = self.login(password='wrong-password', email='nobody@example.com')
        verified_user = self.make_user(email='old@example.com', name='Old', college_id='SSA-O')
        verified = self.login(password='wrong-password', email=verified_user.email)

        self.assert_error(unverified, 401, 'invalid_credentials')
        self.assertEqual(unverified.json(), unknown.json())
        self.assertEqual(unverified.json(), verified.json())

    def test_login_works_once_verified(self):
        self.verify(self.emailed_code())
        self.assertEqual(self.login().status_code, 200)

    def test_accounts_that_existed_before_verification_can_still_log_in(self):
        # What migration 0004 does for real accounts.
        old = self.make_user(email='old@example.com', name='Old', college_id='SSA-O')
        self.assertTrue(old.email_verified)
        self.assertEqual(self.login(email='old@example.com').status_code, 200)

    def test_signing_up_again_with_an_unverified_email_is_refused(self):
        response = self.client.post(SIGNUP, {
            'email': EMAIL, 'password': PASSWORD, 'name': 'Someone Else', 'college_id': 'SSA-X',
        }, format='json')
        self.assert_error(response, 400, 'validation_error', field='email')
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(User.objects.get().name, 'Priya')


class CodeStorageTests(VerificationTestCase):
    def test_code_is_never_stored_in_plain_text(self):
        self.signup()
        code = self.emailed_code()
        record = self.record()

        self.assertNotEqual(record.code_hash, code)
        self.assertEqual(len(record.code_hash), 64)                          # SHA-256, hex
        self.assertRegex(record.code_hash, r'^[0-9a-f]{64}$')
        # The code appears in no column of the row, or of the user's row.
        for obj in [record, record.user]:
            for field in obj._meta.concrete_fields:
                self.assertNotIn(code, str(getattr(obj, field.attname)), field.name)

    def test_hash_is_bound_to_the_user_and_the_server_secret(self):
        self.assertNotEqual(verification.hash_code(1, '123456'), verification.hash_code(2, '123456'))
        self.assertEqual(verification.hash_code(1, '123456'), verification.hash_code(1, '123456'))
        with self.settings(SECRET_KEY='a-different-server-secret'):
            other = verification.hash_code(1, '123456')
        self.assertNotEqual(other, verification.hash_code(1, '123456'))

    def test_codes_are_six_digits_and_come_from_the_secrets_module(self):
        codes = {verification.new_code() for _ in range(200)}
        self.assertTrue(all(re.fullmatch(r'\d{6}', code) for code in codes))
        self.assertGreater(len(codes), 150)                                   # not a constant or a counter
        with mock.patch('accounts.verification.secrets.randbelow', return_value=42) as randbelow:
            self.assertEqual(verification.new_code(), '000042')              # leading zeros kept
        randbelow.assert_called_once_with(1_000_000)

    def test_code_is_not_in_any_api_response(self):
        signup = self.signup()
        code = self.emailed_code()
        self.assertNotIn(code, signup.content.decode())
        self.age_code(seconds=61)
        resend = self.client.post(RESEND, {'email': EMAIL}, format='json')
        self.assertNotIn(self.emailed_code(), resend.content.decode())


class MailBackendSettingTests(VerificationTestCase):
    """The backend is chosen by the environment. Settings are evaluated in a
    child process so the real environment and settings are untouched.
    """

    def mailers(self, **env):
        import json
        import os
        import subprocess
        import sys

        clean = {k: v for k, v in os.environ.items() if not k.startswith('EMAIL_') and k != 'DEFAULT_FROM_EMAIL'}
        # Blank values override anything in a developer's .env file.
        clean.update({'EMAIL_HOST': '', 'DEFAULT_FROM_EMAIL': ''}, **env)
        output = subprocess.run(
            [sys.executable, '-c',
             'import json, django; from django.conf import settings; '
             'print(json.dumps([settings.MAILERS, settings.DEFAULT_FROM_EMAIL]))'],
            env={**clean, 'DJANGO_SETTINGS_MODULE': 'config.settings'}, capture_output=True, text=True, check=True,
        ).stdout
        return json.loads(output.strip().splitlines()[-1])

    def test_console_backend_by_default(self):
        mailers, sender = self.mailers()
        self.assertEqual(mailers, {'default': {'BACKEND': 'django.core.mail.backends.console.EmailBackend'}})
        self.assertIn('Campus League', sender)

    def test_smtp_backend_when_email_host_is_set(self):
        mailers, sender = self.mailers(
            EMAIL_HOST='smtp.example.test', EMAIL_PORT='2525', EMAIL_HOST_USER='mailer',
            EMAIL_HOST_PASSWORD='not-a-real-password', EMAIL_USE_TLS='false', DEFAULT_FROM_EMAIL='Club <club@example.test>',
        )
        self.assertEqual(mailers['default']['BACKEND'], 'django.core.mail.backends.smtp.EmailBackend')
        self.assertEqual(mailers['default']['OPTIONS'], {
            'host': 'smtp.example.test', 'port': 2525, 'username': 'mailer',
            'password': 'not-a-real-password', 'use_tls': False, 'timeout': 10,
        })
        self.assertEqual(sender, 'Club <club@example.test>')

    def test_smtp_defaults_to_port_587_with_tls(self):
        mailers, _ = self.mailers(EMAIL_HOST='smtp.example.test', EMAIL_PORT='', EMAIL_USE_TLS='')
        self.assertEqual((mailers['default']['OPTIONS']['port'], mailers['default']['OPTIONS']['use_tls']), (587, True))
