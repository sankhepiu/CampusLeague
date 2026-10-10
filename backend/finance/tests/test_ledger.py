from django.db import IntegrityError, connection, transaction
from django.test import TestCase, TransactionTestCase

from finance.models import LedgerAccount, LedgerEntry, LedgerLine
from finance.services import LedgerError, account_balance, post_entry

DUES = [('1000', 50000, 0), ('4000', 0, 50000)]


def post(lines=DUES, source_id=1, kind='membership_dues', **extra):
    return post_entry(
        description='Test entry', source_type='payment', source_id=source_id,
        kind=kind, lines=lines, **extra,
    )


def commit_point():
    """Run the checks PostgreSQL would run at COMMIT.

    TestCase never commits (it rolls each test back), so the deferred
    balance trigger would not fire by itself.
    """
    connection.check_constraints()


class StarterAccountTests(TestCase):
    def test_plan_starter_accounts_exist(self):
        accounts = dict(LedgerAccount.objects.values_list('code', 'type'))
        self.assertEqual(accounts, {
            '1000': 'asset',
            '2000': 'liability',
            '4000': 'revenue',
            '4100': 'revenue',
            '4200': 'revenue',
            '4300': 'revenue',
            '5000': 'expense',
            '5100': 'expense',
            '5200': 'expense',
        })


class PostEntryTests(TestCase):
    def test_balanced_entry_is_saved_with_its_lines(self):
        entry = post()
        commit_point()

        self.assertEqual(LedgerEntry.objects.count(), 1)
        self.assertEqual(
            sorted(entry.lines.values_list('account__code', 'debit', 'credit')),
            [('1000', 50000, 0), ('4000', 0, 50000)],
        )
        self.assertEqual((entry.source_type, entry.source_id, entry.kind), ('payment', 1, 'membership_dues'))

    def test_entry_with_several_lines_balances_on_totals(self):
        post(lines=[('1000', 70000, 0), ('4000', 0, 50000), ('4200', 0, 20000)])
        commit_point()
        self.assertEqual(LedgerLine.objects.count(), 3)

    def assert_rejected(self, lines):
        with self.assertRaises(LedgerError):
            post(lines=lines)
        self.assertEqual(LedgerEntry.objects.count(), 0)
        self.assertEqual(LedgerLine.objects.count(), 0)

    def test_unbalanced_entry_is_rejected(self):
        self.assert_rejected([('1000', 50000, 0), ('4000', 0, 49999)])

    def test_off_by_one_paisa_is_rejected(self):
        self.assert_rejected([('1000', 1, 0), ('4000', 0, 2)])

    def test_single_line_is_rejected(self):
        self.assert_rejected([('1000', 50000, 0)])

    def test_no_lines_is_rejected(self):
        self.assert_rejected([])

    def test_zero_amount_line_is_rejected(self):
        self.assert_rejected([('1000', 0, 0), ('4000', 0, 0)])

    def test_negative_amounts_are_rejected(self):
        self.assert_rejected([('1000', -50000, 0), ('4000', 0, -50000)])

    def test_line_with_both_debit_and_credit_is_rejected(self):
        self.assert_rejected([('1000', 50000, 50000), ('4000', 50000, 50000)])

    def test_non_integer_amounts_are_rejected(self):
        for bad in [500.0, '500', None, True]:
            with self.subTest(amount=bad):
                self.assert_rejected([('1000', bad, 0), ('4000', 0, 500)])

    def test_unknown_account_is_rejected_and_nothing_is_saved(self):
        self.assert_rejected([('1000', 50000, 0), ('9999', 0, 50000)])


class DoublePostingTests(TestCase):
    """Plan: "A unique constraint on (source type, source id, kind) means a
    retry cannot post twice."
    """

    def test_same_source_cannot_be_posted_twice(self):
        post()
        with self.assertRaises(IntegrityError), transaction.atomic():
            post()
        self.assertEqual(LedgerEntry.objects.count(), 1)
        self.assertEqual(LedgerLine.objects.count(), 2)
        self.assertEqual(account_balance('1000'), 50000)

    def test_second_post_with_a_different_amount_is_still_refused(self):
        post()
        with self.assertRaises(IntegrityError), transaction.atomic():
            post(lines=[('1000', 1, 0), ('4000', 0, 1)])
        self.assertEqual(account_balance('4000'), 50000)

    def test_different_source_id_is_a_different_entry(self):
        post(source_id=1)
        post(source_id=2)
        self.assertEqual(LedgerEntry.objects.count(), 2)

    def test_same_source_with_a_different_kind_is_allowed(self):
        # Why kind is in the constraint: one source, two financial events.
        post(kind='membership_dues')
        post(kind='other_kind')
        commit_point()
        self.assertEqual(LedgerEntry.objects.count(), 2)


class DatabaseGuardTests(TestCase):
    """The same rules, enforced by PostgreSQL when the service is bypassed."""

    def setUp(self):
        self.cash = LedgerAccount.objects.get(code='1000')
        self.dues = LedgerAccount.objects.get(code='4000')

    def raw_entry(self, source_id=99):
        return LedgerEntry.objects.create(
            description='raw', source_type='payment', source_id=source_id, kind='membership_dues',
        )

    def assert_line_refused(self, **amounts):
        # The entry is created inside the savepoint so it is rolled back
        # with the refused line; a line-less entry left behind would itself
        # (correctly) fail the balance check at the end of the test.
        with self.assertRaises(IntegrityError), transaction.atomic():
            entry = self.raw_entry()
            LedgerLine.objects.create(entry=entry, account=self.cash, **amounts)
        self.assertEqual(LedgerLine.objects.count(), 0)

    def test_negative_line_is_refused(self):
        self.assert_line_refused(debit=-100, credit=0)

    def test_zero_line_is_refused(self):
        self.assert_line_refused(debit=0, credit=0)

    def test_line_with_both_sides_is_refused(self):
        self.assert_line_refused(debit=100, credit=100)

    def test_unbalanced_entry_cannot_be_committed(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            entry = self.raw_entry()
            LedgerLine.objects.create(entry=entry, account=self.cash, debit=50000)
            LedgerLine.objects.create(entry=entry, account=self.dues, credit=49999)
            commit_point()
        self.assertEqual(LedgerEntry.objects.count(), 0)

    def test_one_sided_entry_cannot_be_committed(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            entry = self.raw_entry()
            LedgerLine.objects.create(entry=entry, account=self.cash, debit=50000)
            commit_point()

    def test_entry_without_lines_cannot_be_committed(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.raw_entry()
            commit_point()

    def test_balanced_raw_entry_is_accepted(self):
        entry = self.raw_entry()
        LedgerLine.objects.create(entry=entry, account=self.cash, debit=50000)
        LedgerLine.objects.create(entry=entry, account=self.dues, credit=50000)
        commit_point()

    def test_entry_cannot_be_updated(self):
        entry = post()
        with self.assertRaises(IntegrityError), transaction.atomic():
            LedgerEntry.objects.filter(pk=entry.pk).update(description='edited')
        entry.refresh_from_db()
        self.assertEqual(entry.description, 'Test entry')

    def test_entry_cannot_be_saved_again(self):
        entry = post()
        entry.description = 'edited'
        with self.assertRaises(IntegrityError), transaction.atomic():
            entry.save()

    def test_line_amount_cannot_be_updated(self):
        post()
        with self.assertRaises(IntegrityError), transaction.atomic():
            LedgerLine.objects.filter(debit=50000).update(debit=1)
        self.assertEqual(account_balance('1000'), 50000)

    def test_line_cannot_be_deleted(self):
        post()
        with self.assertRaises(IntegrityError), transaction.atomic():
            LedgerLine.objects.all().delete()
        self.assertEqual(LedgerLine.objects.count(), 2)

    def test_entry_cannot_be_deleted_even_with_raw_sql(self):
        entry = post()
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('DELETE FROM finance_ledgerline WHERE entry_id = %s', [entry.pk])
        self.assertEqual(LedgerLine.objects.count(), 2)

    def test_account_with_lines_cannot_be_deleted(self):
        post()
        with self.assertRaises(Exception) as caught, transaction.atomic():
            self.cash.delete()
        self.assertEqual(type(caught.exception).__name__, 'ProtectedError')


class BalanceTests(TestCase):
    def test_empty_ledger_has_zero_balances(self):
        self.assertEqual(account_balance('1000'), 0)
        self.assertEqual(account_balance('4000'), 0)

    def test_asset_grows_with_debits_and_revenue_with_credits(self):
        post(source_id=1)
        post(source_id=2, lines=[('1000', 20000, 0), ('4000', 0, 20000)])
        self.assertEqual(account_balance('1000'), 70000)
        self.assertEqual(account_balance('4000'), 70000)

    def test_expense_and_liability_sides(self):
        # The plan's "expense request approved" posting.
        post(lines=[('5000', 30000, 0), ('2000', 0, 30000)])
        self.assertEqual(account_balance('5000'), 30000)
        self.assertEqual(account_balance('2000'), 30000)
        self.assertEqual(account_balance('1000'), 0)

    def test_opposite_side_reduces_the_balance(self):
        post(source_id=1)
        post(source_id=2, lines=[('4000', 20000, 0), ('1000', 0, 20000)])
        self.assertEqual(account_balance('1000'), 30000)
        self.assertEqual(account_balance('4000'), 30000)

    def test_total_debits_equal_total_credits_across_the_ledger(self):
        post(source_id=1)
        post(source_id=2, lines=[('5000', 30000, 0), ('2000', 0, 30000)])
        post(source_id=3, lines=[('1000', 70000, 0), ('4000', 0, 50000), ('4200', 0, 20000)])
        debit = sum(LedgerLine.objects.values_list('debit', flat=True))
        credit = sum(LedgerLine.objects.values_list('credit', flat=True))
        self.assertEqual(debit, credit)
        self.assertEqual(debit, 150000)


class RealCommitTests(TransactionTestCase):
    """Uses real COMMITs (no test-wrapping transaction), so the deferred
    trigger fires exactly as it would in production.
    """

    # Restores migration data (the starter accounts) after each test's flush.
    serialized_rollback = True

    def test_commit_of_unbalanced_entry_fails_and_leaves_nothing(self):
        cash = LedgerAccount.objects.get(code='1000')
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                entry = LedgerEntry.objects.create(
                    description='raw', source_type='payment', source_id=1, kind='membership_dues',
                )
                LedgerLine.objects.create(entry=entry, account=cash, debit=50000)
            # Leaving the block is the COMMIT; that is where it fails.
        self.assertEqual(LedgerEntry.objects.count(), 0)
        self.assertEqual(LedgerLine.objects.count(), 0)

    def test_commit_of_balanced_entry_succeeds(self):
        with transaction.atomic():
            post()
        self.assertEqual(LedgerEntry.objects.count(), 1)
        self.assertEqual(account_balance('1000'), 50000)
