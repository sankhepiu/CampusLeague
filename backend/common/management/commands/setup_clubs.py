from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from common import seed, seed_clubs
from common.clubs import schema_of, set_search_path, use_club
from finance import reports


class Command(BaseCommand):
    help = (
        'Create, migrate and seed the database schema of every club except Skyline '
        '(which lives in "public" and is seeded by seed_demo). Safe to run again. Development only.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help="Wipe and rebuild each club's demo data.")
        parser.add_argument('--club', help='Only this club (a slug from settings.CLUBS).')

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('Refusing to run: DJANGO_DEBUG is not true. This command creates demo accounts.')
        slugs = [slug for slug in settings.CLUBS if schema_of(slug) != 'public']
        if options['club']:
            if options['club'] not in slugs:
                raise CommandError(f"--club must be one of: {', '.join(slugs)}")
            slugs = [options['club']]

        try:
            for slug in slugs:
                self.setup(slug, options['reset'])
        finally:
            # Whatever happened, leave the connection where it started.
            set_search_path('public')

    def setup(self, slug, reset):
        schema, out = schema_of(slug), self.stdout.write
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS {connection.ops.quote_name(schema)}')

        with use_club(slug) as club:
            # With the search path on this schema alone, migrate sees no
            # django_migrations table and builds everything here: tables,
            # CHECK constraints, the ledger and audit trigger functions.
            # On a later run it finds them and has nothing to do.
            call_command('migrate', interactive=False, verbosity=0)

            seeded = get_user_model().objects.exists()
            if seeded and not reset:
                out(f"{club['name']}: schema \"{schema}\" is up to date; demo data kept (use --reset to rebuild).")
            else:
                if seeded:
                    seed.reset()
                accounts = seed_clubs.seed_club(slug)
                seed.remove_orphan_receipts()
                out(self.style.SUCCESS(f"{club['name']}: schema \"{schema}\" migrated and seeded."))
                for prefix, email in accounts['leaders'].items():
                    out(f'  {prefix:12} {email}')
                out(f"  {'member':12} {accounts['member']}")
                if accounts['shared']:
                    out(f"  also members here (and of Skyline): {', '.join(accounts['shared'])}")

            check = reports.reconcile()
            passed = sum(item['ok'] for item in check['checks'])
            out(f"  reconciliation: {passed} of {len(check['checks'])} checks pass")
        out(f'  password for all: {seed.DEMO_PASSWORD}')
