from django.core.management.base import BaseCommand

from members.renewals import run_daily_job


class Command(BaseCommand):
    help = 'Mark expired memberships as lapsed and email renewal reminders. Run once a day.'

    def handle(self, *args, **options):
        result = run_daily_job()
        self.stdout.write(
            f"Lapsed: {result['lapsed']}  "
            f"Reminders sent: {result['reminders_sent']}  "
            f"Reminders failed: {result['reminders_failed']}"
        )
