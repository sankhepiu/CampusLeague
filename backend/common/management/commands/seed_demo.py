from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from common import seed
from events.models import Event, Ticket
from finance.models import LedgerEntry
from finance.services import account_balance
from members.models import Membership


class Command(BaseCommand):
    help = 'Wipe and rebuild the Skyline demo data. Development only.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset', action='store_true',
            help='Delete ALL users, memberships, events, tickets, orders, ledger and audit rows first.',
        )

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError(
                'Refusing to run: DJANGO_DEBUG is not true. This command creates accounts '
                'with a published password and can erase the ledger.'
            )
        if not options['reset'] and get_user_model().objects.exists():
            raise CommandError('The database already has users. Re-run with --reset to wipe and rebuild.')

        # One transaction: a failure part-way leaves the previous data intact.
        with transaction.atomic():
            if options['reset']:
                seed.reset()
            data = seed.seed()

        out = self.stdout.write
        out(self.style.SUCCESS('Demo data ready: Skyline Student Association'))
        out(f"  users {get_user_model().objects.count()}   memberships {Membership.objects.count()}"
            f"   events {Event.objects.count()}   tickets {Ticket.objects.count()}"
            f"   ledger entries {LedgerEntry.objects.count()}")
        out(f"  cash Rs {account_balance('1000') / 100:,.2f}"
            f"   dues Rs {account_balance('4000') / 100:,.2f}"
            f"   ticket revenue Rs {account_balance('4100') / 100:,.2f}")
        out('')
        out(f'Demo logins (password for all: {seed.DEMO_PASSWORD})')
        for prefix, _, role in seed.LEADERS:
            out(f"  {role:22} {data['leaders'][prefix].email}")
        out(f"  {'active member':22} {data['members'][0].email}")
        out(f"  {'expiring in 3 days':22} {data['expiring'][1].email}")
        out(f"  {'lapsed member':22} {data['lapsed'][0].email}")
        out(f"  {'Django admin':22} {data['admin'].email}   (http://127.0.0.1:8000/admin/)")
        out('')
        out(f'Priya has no account yet: sign her up live as priya@{seed.DOMAIN}.')
