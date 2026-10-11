"""Several clubs on one site: one PostgreSQL schema per club.

Skyline is the "public" schema every other test runs in. These tests build
a second club's schema (robotics) with the real setup code, and check that
the two cannot see each other.
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import TransactionTestCase, override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from common import clubs, seed
from common.clubs import use_club
from events.models import Event
from finance import reports
from finance.models import LedgerEntry, receipt_folder
from finance.services import account_balance
from members.models import MembershipPlan
from shop.payments import purchase_membership

User = get_user_model()
PASSWORD = 'correct-horse-battery'
SKYLINE = {'slug': 'skyline', 'name': 'Skyline Student Association', 'short': 'SSA', 'color': '#f5c542'}
ROBOTICS = {'slug': 'robotics', 'name': 'Pixel Robotics Club', 'short': 'PRC', 'color': '#4fd1c5'}


def search_path():
    with connection.cursor() as cursor:
        cursor.execute('SHOW search_path')
        return cursor.fetchone()[0]


def make_user(email, **extra):
    fields = {'name': 'Priya', 'college_id': 'SSA-001', 'email_verified': True}
    fields.update(extra)
    return User.objects.create_user(email=email, password=PASSWORD, **fields)


# Real commits: creating a schema and migrating it is DDL, and the point is
# what a second request on the same connection sees afterwards.
@override_settings(DEBUG=True)
class ClubSchemaTests(TransactionTestCase):
    serialized_rollback = True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with connection.cursor() as cursor:
            cursor.execute('DROP SCHEMA IF EXISTS robotics CASCADE')
            cursor.execute('CREATE SCHEMA robotics')
        with use_club('robotics'):
            call_command('migrate', interactive=False, verbosity=0)

    @classmethod
    def tearDownClass(cls):
        clubs.set_search_path('public')
        with connection.cursor() as cursor:
            cursor.execute('DROP SCHEMA IF EXISTS robotics CASCADE')
        super().tearDownClass()

    def setUp(self):
        cache.clear()
        with use_club('robotics'):
            seed.reset()                    # robotics tables are not flushed between tests
        self.client = APIClient()

    def get(self, path, club=None, token=None):
        headers = {}
        if club:
            headers['HTTP_X_CLUB'] = club
        if token:
            headers['HTTP_AUTHORIZATION'] = f'Token {token}'
        return self.client.get(path, **headers)

    def login(self, email='priya@example.com', password=PASSWORD, **body):
        return self.client.post('/api/auth/login', {'email': email, 'password': password, **body}, format='json')

    # Setup ----------------------------------------------------------------

    def test_the_club_schema_is_a_complete_copy_with_its_own_triggers(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'robotics'"
            )
            robotics_tables = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
            public_tables = cursor.fetchone()[0]
            cursor.execute(
                "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                "WHERE n.nspname = 'robotics' AND p.proname IN ('finance_ledger_append_only', 'audit_log_append_only')"
            )
            trigger_functions = cursor.fetchone()[0]
        self.assertEqual(robotics_tables, public_tables)
        self.assertGreater(robotics_tables, 30)
        self.assertEqual(trigger_functions, 2)

    def test_the_ledger_is_append_only_in_a_club_schema_too(self):
        from django.db import IntegrityError, transaction

        with use_club('robotics'):
            plan = MembershipPlan.objects.create(name='Builder', price=40000, duration_months=12)
            purchase_membership(
                user=make_user('priya@example.com'), plan=plan, outcome='success', idempotency_key='robotics-key-0001',
            )
            with self.assertRaises(IntegrityError), transaction.atomic():
                LedgerEntry.objects.update(description='edited')
            self.assertEqual(LedgerEntry.objects.get().description, 'Membership dues: Builder')

    # Middleware -------------------------------------------------------------

    def test_search_path_is_set_for_the_request_and_reset_afterwards(self):
        seen = {}

        def view(request):
            seen['path'], seen['club'], seen['current'] = search_path(), request.club, clubs.current_club()
            from django.http import HttpResponse
            return HttpResponse('ok')

        from django.test import RequestFactory

        middleware = clubs.ClubMiddleware(view)
        middleware(RequestFactory().get('/', HTTP_X_CLUB='robotics'))
        self.assertEqual((seen['path'], seen['club'], seen['current']), ('robotics', ROBOTICS, 'robotics'))
        self.assertEqual((search_path(), clubs.current_club()), ('public', 'skyline'))

        middleware(RequestFactory().get('/'))                   # no header: skyline
        self.assertEqual((seen['path'], seen['club']), ('public', SKYLINE))
        middleware(RequestFactory().get('/', HTTP_X_CLUB=' Robotics '))
        self.assertEqual(seen['path'], 'robotics')

    def test_search_path_is_reset_even_when_the_view_raises(self):
        from django.test import RequestFactory

        def view(request):
            raise RuntimeError('boom')

        with self.assertRaises(RuntimeError):
            clubs.ClubMiddleware(view)(RequestFactory().get('/', HTTP_X_CLUB='robotics'))
        self.assertEqual((search_path(), clubs.current_club()), ('public', 'skyline'))

    def test_unknown_club_is_a_404(self):
        for slug in ['chess', 'public', 'robotics; drop schema public', '../music']:
            with self.subTest(slug=slug):
                response = self.get('/api/plans', club=slug)
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json()['code'], 'club_not_found')
                self.assertEqual(set(response.json()), {'code', 'message', 'field'})
        self.assertEqual(search_path(), 'public')

    def test_a_club_whose_schema_has_not_been_set_up_is_a_404(self):
        # "music" is in settings.CLUBS, but nothing has created its schema here.
        self.assertEqual(self.get('/api/plans', club='music').json()['code'], 'club_not_found')
        self.assertEqual(self.get('/api/plans', club='robotics').status_code, 200)

    def test_clubs_are_listed_publicly(self):
        response = self.get('/api/clubs')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[:2], [SKYLINE, ROBOTICS])
        self.assertEqual([club['slug'] for club in response.json()], ['skyline', 'robotics', 'music'])

    # Isolation --------------------------------------------------------------

    def test_data_created_in_one_club_is_not_visible_in_the_other(self):
        MembershipPlan.objects.create(name='Skyline Basic', price=50000, duration_months=12)
        with use_club('robotics'):
            MembershipPlan.objects.create(name='Builder', price=40000, duration_months=12)
            self.assertEqual(list(MembershipPlan.objects.values_list('name', flat=True)), ['Builder'])
        self.assertEqual(list(MembershipPlan.objects.values_list('name', flat=True)), ['Skyline Basic'])

        names = lambda response: [plan['name'] for plan in response.json()['results']]
        self.assertEqual(names(self.get('/api/plans')), ['Skyline Basic'])
        self.assertEqual(names(self.get('/api/plans', club='skyline')), ['Skyline Basic'])
        self.assertEqual(names(self.get('/api/plans', club='robotics')), ['Builder'])

    def test_an_id_from_one_club_does_not_open_the_other_clubs_row(self):
        from datetime import timedelta

        from django.utils import timezone

        starts = timezone.now() + timedelta(days=5)
        with use_club('robotics'):
            event = Event.objects.create(
                title='Robo Wars', venue='Quad', starts_at=starts, ends_at=starts + timedelta(hours=2),
                capacity_total=10, status='on_sale',
            )
        self.assertEqual(self.get(f'/api/events/{event.pk}', club='robotics').json()['title'], 'Robo Wars')
        self.assertEqual(self.get(f'/api/events/{event.pk}', club='skyline').status_code, 404)
        self.assertEqual(self.get('/api/events', club='skyline').json()['count'], 0)

    def test_money_and_reconciliation_are_per_club(self):
        skyline_plan = MembershipPlan.objects.create(name='Basic', price=50000, duration_months=12)
        purchase_membership(
            user=make_user('priya@example.com'), plan=skyline_plan, outcome='success', idempotency_key='skyline-key-0001',
        )
        with use_club('robotics'):
            plan = MembershipPlan.objects.create(name='Builder', price=40000, duration_months=12)
            for number in range(2):
                purchase_membership(
                    user=make_user(f'bot{number}@example.com', college_id=f'PRC-{number}'), plan=plan,
                    outcome='success', idempotency_key=f'robotics-key-{number:04}',
                )
            self.assertEqual(account_balance('1000'), 80000)
            result = reports.reconcile()
            self.assertEqual((result['ok'], len(result['checks'])), (True, 11))
        self.assertEqual(account_balance('1000'), 50000)
        result = reports.reconcile()
        self.assertEqual((result['ok'], len(result['checks'])), (True, 11))

    def test_receipts_are_stored_per_club(self):
        self.assertEqual(receipt_folder(), 'receipts/')
        with use_club('robotics'):
            self.assertEqual(receipt_folder(), 'receipts/robotics/')
        self.assertEqual(receipt_folder('music'), 'receipts/music/')

    # Login ------------------------------------------------------------------

    def test_login_finds_the_one_club_an_account_is_in(self):
        with use_club('robotics'):
            user = make_user('bot@example.com')
        response = self.login('bot@example.com')
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(set(body), {'token', 'user', 'club'})
        self.assertEqual(body['club'], ROBOTICS)
        self.assertEqual(body['user']['email'], 'bot@example.com')
        with use_club('robotics'):
            self.assertEqual(Token.objects.get(user=user).key, body['token'])
        self.assertEqual(Token.objects.count(), 0)                 # nothing in skyline
        self.assertEqual(search_path(), 'public')

        make_user('sky@example.com')
        self.assertEqual(self.login('sky@example.com').json()['club'], SKYLINE)

    def test_account_in_two_clubs_must_choose(self):
        make_user('priya@example.com')
        with use_club('robotics'):
            make_user('priya@example.com')

        response = self.login()
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json(), {
            'code': 'choose_club',
            'message': 'This account belongs to more than one club. Choose which one to open.',
            'field': None,
            'clubs': [SKYLINE, ROBOTICS],
        })
        # No token was issued in either club.
        self.assertEqual(Token.objects.count(), 0)
        with use_club('robotics'):
            self.assertEqual(Token.objects.count(), 0)

        for slug, club in [('robotics', ROBOTICS), ('skyline', SKYLINE)]:
            chosen = self.login(club=slug)
            self.assertEqual(chosen.status_code, 200, chosen.content)
            self.assertEqual(chosen.json()['club'], club)

    def test_same_email_with_different_passwords_logs_in_where_the_password_fits(self):
        make_user('priya@example.com')
        with use_club('robotics'):
            User.objects.create_user(
                email='priya@example.com', password='another-long-secret', name='Priya', college_id='PRC-1',
                email_verified=True,
            )
        self.assertEqual(self.login().json()['club'], SKYLINE)
        self.assertEqual(self.login(password='another-long-secret').json()['club'], ROBOTICS)
        # The right password for one club does not open the other.
        self.assertEqual(self.login(club='robotics').json()['code'], 'invalid_credentials')

    def test_login_with_an_explicit_club(self):
        with use_club('robotics'):
            make_user('bot@example.com')
        self.assertEqual(self.login('bot@example.com', club='robotics').status_code, 200)
        self.assertEqual(self.login('bot@example.com', club='ROBOTICS').status_code, 200)
        wrong = self.login('bot@example.com', club='skyline')
        self.assertEqual((wrong.status_code, wrong.json()['code']), (401, 'invalid_credentials'))
        for slug in ['chess', 'music']:                        # unknown, and not set up
            missing = self.login('bot@example.com', club=slug)
            self.assertEqual((missing.status_code, missing.json()['code']), (404, 'club_not_found'))

    def test_wrong_password_everywhere_is_the_usual_error(self):
        make_user('priya@example.com')
        with use_club('robotics'):
            make_user('priya@example.com')
        for response in [self.login(password='nope-nope-nope'), self.login('nobody@example.com')]:
            self.assertEqual((response.status_code, response.json()['code']), (401, 'invalid_credentials'))

    def test_unverified_account_is_told_to_verify(self):
        with use_club('robotics'):
            make_user('new@example.com', email_verified=False)
        response = self.login('new@example.com')
        self.assertEqual((response.status_code, response.json()['code']), (403, 'email_not_verified'))

    # Tokens -----------------------------------------------------------------

    def test_a_token_from_one_club_is_refused_in_another(self):
        with use_club('robotics'):
            make_user('bot@example.com')
        token = self.login('bot@example.com').json()['token']

        mine = self.get('/api/auth/me', club='robotics', token=token)
        self.assertEqual(mine.status_code, 200, mine.content)
        self.assertEqual((mine.json()['email'], mine.json()['club']), ('bot@example.com', ROBOTICS))

        for club in ['skyline', None]:                         # no header means skyline
            other = self.get('/api/auth/me', club=club, token=token)
            self.assertEqual((other.status_code, other.json()['code']), (401, 'authentication_failed'))
        self.assertEqual(self.get('/api/orders/me', club='skyline', token=token).status_code, 401)
        self.assertEqual(self.get('/api/orders/me', club='robotics', token=token).status_code, 200)

    def test_signup_goes_to_the_club_in_the_header(self):
        body = {'email': 'new@example.com', 'password': PASSWORD, 'name': 'New Person', 'college_id': 'PRC-900'}
        response = self.client.post('/api/auth/signup', body, format='json', HTTP_X_CLUB='robotics')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertFalse(User.objects.filter(email='new@example.com').exists())
        with use_club('robotics'):
            self.assertTrue(User.objects.filter(email='new@example.com').exists())

    def test_razorpay_checkout_is_named_after_the_club(self):
        from unittest import mock

        from shop.tests.test_razorpay import RAZORPAY_ON, FakeRazorpay

        with use_club('robotics'):
            make_user('bot@example.com')
            plan = MembershipPlan.objects.create(name='Builder', price=40000, duration_months=12)
        token = self.login('bot@example.com').json()['token']
        with RAZORPAY_ON, mock.patch('shop.razorpay.urlopen', FakeRazorpay()):
            response = self.client.post(
                '/api/payments/razorpay/order', {'purpose': 'membership', 'plan': plan.pk}, format='json',
                HTTP_X_CLUB='robotics', HTTP_AUTHORIZATION=f'Token {token}', HTTP_IDEMPOTENCY_KEY='robotics-rzp-0001',
            )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual((response.json()['name'], response.json()['amount']), ('Pixel Robotics Club', 40000))

    # The real seed ------------------------------------------------------------

    def test_setup_clubs_seeds_a_club_that_reconciles_and_is_idempotent(self):
        import io
        import shutil
        import tempfile

        media = tempfile.mkdtemp(prefix='campusleague-test-media-')
        self.addCleanup(shutil.rmtree, media, True)
        with override_settings(MEDIA_ROOT=media):
            out = io.StringIO()
            call_command('setup_clubs', club='robotics', stdout=out)
            self.assertIn('11 of 11 checks pass', out.getvalue())
            with use_club('robotics'):
                counts = (User.objects.count(), Event.objects.count(), LedgerEntry.objects.count())
                # 5 leaders + 15 members + the 5 Skyline members who also joined;
                # 3 named events + 37 generated ones.
                self.assertEqual(counts[:2], (25, 40))
                self.assertTrue(User.objects.filter(email='member01@skyline.test').exists())
                self.assertTrue(User.objects.filter(email='president@robotics.test').exists())
                self.assertTrue(reports.reconcile()['ok'])
            # Skyline got nothing from it.
            self.assertEqual((User.objects.count(), Event.objects.count(), LedgerEntry.objects.count()), (0, 0, 0))

            again = io.StringIO()
            call_command('setup_clubs', club='robotics', stdout=again)
            self.assertIn('demo data kept', again.getvalue())
            with use_club('robotics'):
                self.assertEqual((User.objects.count(), Event.objects.count(), LedgerEntry.objects.count()), counts)

            import os
            self.assertTrue(os.listdir(os.path.join(media, 'receipts', 'robotics')))
        self.assertEqual(search_path(), 'public')
        self.assertEqual(self.login('president@robotics.test', seed.DEMO_PASSWORD).json()['club'], ROBOTICS)
