import threading
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase

from finance.models import LedgerEntry
from finance.services import account_balance
from members.models import Membership, MembershipPlan
from shop.models import Order, Payment
from shop.payments import IdempotencyConflict, process_payment, purchase_membership

User = get_user_model()


class ConcurrentPurchaseTests(TransactionTestCase):
    """Real simultaneous requests: each thread has its own database
    connection and its own committed transaction, which a normal TestCase
    (one connection, one never-committed transaction) cannot simulate.
    """

    serialized_rollback = True

    def setUp(self):
        self.plan = MembershipPlan.objects.create(name='Basic', price=50000, duration_months=12)
        self.user = User.objects.create_user(
            email='priya@example.com', password='correct-horse-battery',
            name='Priya', college_id='SSA-001',
        )

    def run_together(self, calls):
        """Start every call at the same instant; return results or exceptions."""
        barrier = threading.Barrier(len(calls))
        outcomes = [None] * len(calls)

        def worker(index, kwargs):
            try:
                barrier.wait(timeout=10)
                outcomes[index] = purchase_membership(**kwargs)
            except Exception as exc:
                outcomes[index] = exc
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(i, kw)) for i, kw in enumerate(calls)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertFalse(any(thread.is_alive() for thread in threads), 'a purchase thread hung')
        return outcomes

    def call(self, key, user=None):
        return {
            'user': user or self.user, 'plan': self.plan,
            'outcome': 'success', 'idempotency_key': key,
        }

    def test_same_key_sent_simultaneously_charges_once(self):
        outcomes = self.run_together([self.call('double-click-key')] * 6)

        errors = [outcome for outcome in outcomes if isinstance(outcome, Exception)]
        self.assertEqual(errors, [])
        self.assertEqual(sum(1 for outcome in outcomes if not outcome.replayed), 1)
        self.assertEqual(len({outcome.order.pk for outcome in outcomes}), 1)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Membership.objects.count(), 1)
        self.assertEqual(LedgerEntry.objects.count(), 1)
        self.assertEqual(account_balance('1000'), 50000)

    def test_simultaneous_renewals_get_consecutive_dates(self):
        outcomes = self.run_together([self.call('renewal-key-a'), self.call('renewal-key-b')])

        self.assertEqual([o for o in outcomes if isinstance(o, Exception)], [])
        first, second = Membership.objects.order_by('start_date')
        self.assertEqual(second.start_date, first.end_date + timedelta(days=1))
        self.assertEqual(Payment.objects.count(), 2)
        self.assertEqual(account_balance('4000'), 100000)

    def test_two_users_racing_with_the_same_key_only_one_is_charged(self):
        other = User.objects.create_user(
            email='ravi@example.com', password='correct-horse-battery',
            name='Ravi', college_id='SSA-002',
        )

        outcomes = self.run_together([self.call('shared-key-01'), self.call('shared-key-01', user=other)])

        conflicts = [o for o in outcomes if isinstance(o, IdempotencyConflict)]
        winners = [o for o in outcomes if not isinstance(o, Exception)]
        self.assertEqual((len(winners), len(conflicts)), (1, 1), outcomes)
        # The loser's order was rolled back with everything else.
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(Membership.objects.count(), 1)
        self.assertEqual(LedgerEntry.objects.count(), 1)
        self.assertEqual(account_balance('1000'), 50000)


class GatewayGuardTests(TransactionTestCase):
    serialized_rollback = True

    def test_an_order_that_is_already_paid_cannot_be_paid_again(self):
        plan = MembershipPlan.objects.create(name='Basic', price=50000, duration_months=12)
        user = User.objects.create_user(
            email='priya@example.com', password='correct-horse-battery',
            name='Priya', college_id='SSA-001',
        )
        result = purchase_membership(user=user, plan=plan, outcome='success', idempotency_key='first-key-001')

        with self.assertRaises(ValueError):
            process_payment(result.order, 'success', 'second-key-002')

        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(LedgerEntry.objects.count(), 1)
        self.assertEqual(account_balance('1000'), 50000)
