from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from members.models import Membership
from members.renewals import run_daily_job
from members.tests.test_services import make_plan

User = get_user_model()
DAY = timedelta(days=1)


class DailyJobTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.plan = make_plan()
        self.count = 0

    def member(self, days_left, status='active', length=365):
        self.count += 1
        user = User.objects.create_user(
            email=f'm{self.count}@example.com', password='correct-horse-battery',
            name=f'Member {self.count}', college_id=f'SSA-{self.count}',
        )
        end = self.today + days_left * DAY
        return Membership.objects.create(
            user=user, plan=self.plan, status=status, start_date=end - length * DAY, end_date=end,
        )

    def run_job(self, days_from_now=0):
        return run_daily_job(now=timezone.now() + days_from_now * DAY)

    # Reminders -----------------------------------------------------------

    def test_reminder_sent_when_14_days_remain(self):
        membership = self.member(days_left=14)

        result = self.run_job()

        self.assertEqual(result['reminders_sent'], 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [membership.user.email])
        self.assertIn(self.plan.name, mail.outbox[0].body)
        membership.refresh_from_db()
        self.assertIsNotNone(membership.reminder_sent_at)

    def test_no_reminder_when_15_days_remain(self):
        self.member(days_left=15)
        self.assertEqual(self.run_job()['reminders_sent'], 0)
        self.assertEqual(mail.outbox, [])

    def test_running_twice_on_the_same_day_sends_once(self):
        self.member(days_left=10)
        self.run_job()
        self.run_job()
        self.assertEqual(len(mail.outbox), 1)

    def test_no_second_reminder_between_the_two_windows(self):
        self.member(days_left=14)
        self.run_job(0)
        for day in range(1, 11):      # 13 down to 4 days left
            self.run_job(day)
        self.assertEqual(len(mail.outbox), 1)

    def test_second_reminder_when_3_days_remain(self):
        self.member(days_left=14)
        self.run_job(0)
        self.run_job(11)              # 3 days left
        self.run_job(12)              # 2 days left: no third email
        self.assertEqual(len(mail.outbox), 2)

    def test_reminder_on_the_last_day(self):
        self.member(days_left=0)
        self.assertEqual(self.run_job()['reminders_sent'], 1)

    def test_member_who_already_renewed_is_not_reminded(self):
        membership = self.member(days_left=5)
        Membership.objects.create(
            user=membership.user, plan=self.plan, status='active',
            start_date=membership.end_date + DAY, end_date=membership.end_date + 366 * DAY,
        )
        self.assertEqual(self.run_job()['reminders_sent'], 0)

    def test_cancelled_and_lapsed_memberships_are_not_reminded(self):
        self.member(days_left=5, status='cancelled')
        self.member(days_left=5, status='lapsed')
        self.assertEqual(self.run_job()['reminders_sent'], 0)

    def test_email_failure_is_counted_and_retried_next_run(self):
        membership = self.member(days_left=5)
        self.member(days_left=6)

        with mock.patch('members.renewals.send_mail', side_effect=[OSError('smtp down'), 1]):
            with self.assertLogs('campusleague.renewals', level='ERROR'):
                result = self.run_job()

        self.assertEqual((result['reminders_sent'], result['reminders_failed']), (1, 1))
        membership.refresh_from_db()
        self.assertIsNone(membership.reminder_sent_at)

        self.assertEqual(self.run_job()['reminders_sent'], 1)   # the failed one, retried

    # Lapsing -------------------------------------------------------------

    def test_membership_past_its_end_date_is_marked_lapsed(self):
        membership = self.member(days_left=-1)
        self.assertEqual(self.run_job()['lapsed'], 1)
        membership.refresh_from_db()
        self.assertEqual(membership.status, 'lapsed')
        self.assertEqual(mail.outbox, [])

    def test_membership_ending_today_is_still_active(self):
        membership = self.member(days_left=0)
        self.assertEqual(self.run_job()['lapsed'], 0)
        membership.refresh_from_db()
        self.assertEqual(membership.status, 'active')

    def test_cancelled_membership_is_not_relabelled_lapsed(self):
        membership = self.member(days_left=-10, status='cancelled')
        self.run_job()
        membership.refresh_from_db()
        self.assertEqual(membership.status, 'cancelled')

    def test_command_runs_the_job_and_reports(self):
        self.member(days_left=-1)
        self.member(days_left=3)
        with mock.patch('sys.stdout.write') as write:
            call_command('run_membership_job')
        self.assertIn('Lapsed: 1  Reminders sent: 1  Reminders failed: 0', write.call_args_list[0][0][0])
