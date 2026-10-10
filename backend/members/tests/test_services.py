from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from members.models import Membership, MembershipPlan
from members.services import (
    add_months, current_membership, membership_status, paid_until, start_membership,
)

User = get_user_model()
DAY = timedelta(days=1)


def make_plan(**overrides):
    fields = {
        'name': 'Basic', 'price': 50000, 'duration_months': 12,
        'ticket_discount_pct': 0, 'merch_discount_pct': 10,
    }
    fields.update(overrides)
    return MembershipPlan.objects.create(**fields)


class AddMonthsTests(SimpleTestCase):
    def test_twelve_months_is_the_same_day_next_year(self):
        self.assertEqual(add_months(date(2026, 10, 10), 12), date(2027, 10, 10))

    def test_crossing_a_year_boundary(self):
        self.assertEqual(add_months(date(2026, 11, 15), 3), date(2027, 2, 15))

    def test_day_is_clamped_to_a_shorter_month(self):
        self.assertEqual(add_months(date(2027, 1, 31), 1), date(2027, 2, 28))

    def test_clamped_to_29_february_in_a_leap_year(self):
        self.assertEqual(add_months(date(2028, 1, 31), 1), date(2028, 2, 29))

    def test_leap_day_plus_a_year(self):
        self.assertEqual(add_months(date(2028, 2, 29), 12), date(2029, 2, 28))

    def test_december_plus_one(self):
        self.assertEqual(add_months(date(2026, 12, 31), 1), date(2027, 1, 31))


class PlanConstraintTests(TestCase):
    def assert_refused(self, **overrides):
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_plan(**overrides)
        self.assertEqual(MembershipPlan.objects.count(), 0)

    def test_zero_price_is_refused(self):
        self.assert_refused(price=0)

    def test_zero_duration_is_refused(self):
        self.assert_refused(duration_months=0)

    def test_discount_over_100_is_refused(self):
        self.assert_refused(ticket_discount_pct=101)
        self.assert_refused(merch_discount_pct=101)

    def test_boundary_values_are_accepted(self):
        make_plan(price=1, duration_months=1, ticket_discount_pct=100, merch_discount_pct=0)

    def test_duplicate_name_is_refused(self):
        make_plan()
        with self.assertRaises(IntegrityError), transaction.atomic():
            make_plan()


class MembershipStatusTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.plan = make_plan()
        self.user = User.objects.create_user(
            email='priya@example.com', password='correct-horse-battery',
            name='Priya', college_id='SSA-001',
        )

    def membership(self, start, end, status='active', user=None):
        return Membership.objects.create(
            user=user or self.user, plan=self.plan, status=status, start_date=start, end_date=end,
        )

    def test_no_membership_is_none(self):
        self.assertEqual(membership_status(self.user), 'none')
        self.assertIsNone(current_membership(self.user))
        self.assertIsNone(paid_until(self.user))

    def test_membership_covering_today_is_active(self):
        row = self.membership(self.today - 30 * DAY, self.today + 30 * DAY)
        self.assertEqual(membership_status(self.user), 'active')
        self.assertEqual(current_membership(self.user), row)

    def test_active_on_first_and_last_day(self):
        self.membership(self.today, self.today)
        self.assertEqual(membership_status(self.user), 'active')

    def test_ended_yesterday_is_lapsed_even_if_the_row_still_says_active(self):
        # The nightly job has not run yet; the dates decide.
        self.membership(self.today - 365 * DAY, self.today - DAY, status='active')
        self.assertEqual(membership_status(self.user), 'lapsed')
        self.assertIsNone(current_membership(self.user))

    def test_row_marked_lapsed_is_lapsed(self):
        self.membership(self.today - 365 * DAY, self.today - DAY, status='lapsed')
        self.assertEqual(membership_status(self.user), 'lapsed')

    def test_cancelled_membership_does_not_count(self):
        self.membership(self.today - DAY, self.today + DAY, status='cancelled')
        self.assertEqual(membership_status(self.user), 'none')

    def test_pending_membership_does_not_count(self):
        self.membership(self.today - DAY, self.today + DAY, status='pending')
        self.assertEqual(membership_status(self.user), 'none')

    def test_renewed_after_lapsing_is_active(self):
        self.membership(self.today - 400 * DAY, self.today - 35 * DAY)
        self.membership(self.today - DAY, self.today + 364 * DAY)
        self.assertEqual(membership_status(self.user), 'active')

    def test_another_users_membership_does_not_count(self):
        other = User.objects.create_user(
            email='ravi@example.com', password='correct-horse-battery',
            name='Ravi', college_id='SSA-002',
        )
        self.membership(self.today - DAY, self.today + DAY, user=other)
        self.assertEqual(membership_status(self.user), 'none')

    def test_database_refuses_end_before_start(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.membership(self.today, self.today - DAY)

    def test_database_refuses_unknown_status(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.membership(self.today, self.today, status='platinum')


class StartMembershipTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.plan = make_plan(duration_months=12)
        self.user = User.objects.create_user(
            email='priya@example.com', password='correct-horse-battery',
            name='Priya', college_id='SSA-001',
        )

    def test_first_membership_starts_today_for_the_plan_duration(self):
        row = start_membership(self.user, self.plan)
        self.assertEqual(row.status, 'active')
        self.assertEqual(row.start_date, self.today)
        self.assertEqual(row.end_date, add_months(self.today, 12))
        self.assertEqual(membership_status(self.user), 'active')

    def test_duration_comes_from_the_plan(self):
        term = make_plan(name='Term', duration_months=6)
        row = start_membership(self.user, term)
        self.assertEqual(row.end_date, add_months(self.today, 6))

    def test_renewal_starts_the_day_after_current_cover_ends(self):
        first = start_membership(self.user, self.plan)
        second = start_membership(self.user, self.plan)

        self.assertEqual(second.start_date, first.end_date + DAY)
        self.assertEqual(second.end_date, add_months(second.start_date, 12))
        self.assertEqual(paid_until(self.user), second.end_date)
        # Today is still covered by the first one.
        self.assertEqual(current_membership(self.user), first)

    def test_renewal_after_lapsing_starts_today(self):
        Membership.objects.create(
            user=self.user, plan=self.plan, status='active',
            start_date=self.today - 400 * DAY, end_date=self.today - 35 * DAY,
        )
        row = start_membership(self.user, self.plan)
        self.assertEqual(row.start_date, self.today)
