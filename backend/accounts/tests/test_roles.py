from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.utils import timezone

from accounts.models import RoleAssignment

User = get_user_model()
DAY = timedelta(days=1)


class RoleAssignmentTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.user = User.objects.create_user(
            email='asha@example.com', password='correct-horse-battery',
            name='Asha', college_id='SSA-010',
        )

    def assign(self, role, start, end, user=None):
        return RoleAssignment.objects.create(
            user=user or self.user, role=role, term_start=start, term_end=end,
        )

    def test_no_assignments_means_no_roles(self):
        self.assertEqual(self.user.current_roles(), [])

    def test_term_including_today_is_current(self):
        self.assign('treasurer', self.today - 30 * DAY, self.today + 30 * DAY)
        self.assertEqual(self.user.current_roles(), ['treasurer'])

    def test_term_is_inclusive_on_its_first_and_last_day(self):
        self.assign('treasurer', self.today, self.today + DAY)
        self.assign('president', self.today - DAY, self.today)
        self.assertEqual(self.user.current_roles(), ['president', 'treasurer'])

    def test_one_day_term_today_is_current(self):
        self.assign('event_manager', self.today, self.today)
        self.assertEqual(self.user.current_roles(), ['event_manager'])

    def test_term_that_ended_yesterday_is_not_current(self):
        self.assign('treasurer', self.today - 365 * DAY, self.today - DAY)
        self.assertEqual(self.user.current_roles(), [])

    def test_term_that_starts_tomorrow_is_not_current(self):
        self.assign('treasurer', self.today + DAY, self.today + 365 * DAY)
        self.assertEqual(self.user.current_roles(), [])

    def test_overlapping_terms_for_the_same_role_are_reported_once(self):
        self.assign('treasurer', self.today - 30 * DAY, self.today + DAY)
        self.assign('treasurer', self.today - DAY, self.today + 30 * DAY)
        self.assertEqual(self.user.current_roles(), ['treasurer'])

    def test_roles_belong_to_one_user_only(self):
        other = User.objects.create_user(
            email='ravi@example.com', password='correct-horse-battery',
            name='Ravi', college_id='SSA-011',
        )
        self.assign('president', self.today - DAY, self.today + DAY, user=other)
        self.assertEqual(self.user.current_roles(), [])
        self.assertEqual(other.current_roles(), ['president'])

    def test_database_rejects_term_that_ends_before_it_starts(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.assign('treasurer', self.today, self.today - DAY)
        self.assertEqual(RoleAssignment.objects.count(), 0)

    def test_database_rejects_unknown_role(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.assign('supreme_leader', self.today, self.today)
        self.assertEqual(RoleAssignment.objects.count(), 0)

    def test_user_with_role_history_cannot_be_deleted(self):
        self.assign('treasurer', self.today - 365 * DAY, self.today - DAY)
        with self.assertRaises(ProtectedError):
            self.user.delete()
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
