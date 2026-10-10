from django.core.management.base import BaseCommand

from comms.services import send_pending


class Command(BaseCommand):
    help = 'Send queued announcement emails and retry failed ones (up to 3 attempts each).'

    def handle(self, *args, **options):
        result = send_pending()
        self.stdout.write(f"Sent: {result['sent']}  Failed: {result['failed']}")
