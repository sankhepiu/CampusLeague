from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError, connection, transaction
from django.test import TestCase

User = get_user_model()


class DatabaseBackendTests(TestCase):
    def test_tests_run_on_postgresql(self):
        # Guard: locking and constraint tests later are meaningless on SQLite.
        self.assertEqual(connection.vendor, 'postgresql')


class UserModelTests(TestCase):
    def make_user(self, **overrides):
        fields = {
            'email': 'priya@example.com',
            'password': 'correct-horse-battery',
            'name': 'Priya',
            'college_id': 'SSA-001',
        }
        fields.update(overrides)
        return User.objects.create_user(**fields)

    def test_password_is_hashed_not_stored(self):
        user = self.make_user()
        self.assertNotEqual(user.password, 'correct-horse-battery')
        self.assertNotIn('correct-horse-battery', user.password)
        self.assertTrue(user.check_password('correct-horse-battery'))
        self.assertFalse(user.check_password('wrong-password'))

    def test_login_identifier_is_email(self):
        self.make_user()
        self.assertIsNotNone(
            authenticate(email='priya@example.com', password='correct-horse-battery')
        )
        self.assertIsNone(
            authenticate(email='priya@example.com', password='wrong-password')
        )

    def test_email_is_stored_lowercase(self):
        user = self.make_user(email='  Priya@Example.COM ')
        self.assertEqual(user.email, 'priya@example.com')

    def test_duplicate_email_is_rejected_by_the_database(self):
        self.make_user()
        # atomic() gives the failing INSERT its own savepoint, so the
        # IntegrityError does not poison the test's outer transaction.
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_user(name='Someone Else', college_id='SSA-002')
        self.assertEqual(User.objects.count(), 1)

    def test_duplicate_email_differing_only_by_case_is_rejected(self):
        self.make_user()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_user(email='PRIYA@example.com')
        self.assertEqual(User.objects.count(), 1)

    def test_email_is_required(self):
        with self.assertRaises(ValueError):
            self.make_user(email='')
        self.assertEqual(User.objects.count(), 0)

    def test_new_user_has_no_admin_access(self):
        user = self.make_user()
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_superuser_has_admin_access(self):
        admin = User.objects.create_superuser(
            email='admin@example.com',
            password='correct-horse-battery',
            name='Admin',
            college_id='SSA-000',
        )
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)

    def test_timestamps_are_set(self):
        user = self.make_user()
        self.assertIsNotNone(user.created_at)
        self.assertIsNotNone(user.updated_at)
