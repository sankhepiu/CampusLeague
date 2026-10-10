import threading

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase

from finance.models import LedgerEntry
from finance.services import account_balance
from shop import stock
from shop.models import Order, Payment, StockMovement
from shop.payments import purchase_merch
from shop.stock import OutOfStock
from shop.tests.helpers import make_product, size_of

User = get_user_model()


class LastItemRaceTests(TransactionTestCase):
    """Plan: "Same last-item race on a hoodie size; stock never goes
    negative." Each buyer is a thread with its own connection and its own
    committed transaction, released together.
    """

    serialized_rollback = True

    def race(self, size, buyers, quantity=1):
        users = [
            User.objects.create_user(email=f'buyer{n}@example.com', name=f'Buyer {n}', college_id=f'SSA-{n}')
            for n in range(buyers)
        ]
        barrier = threading.Barrier(buyers)
        outcomes = [None] * buyers

        def worker(index):
            try:
                barrier.wait(timeout=10)
                outcomes[index] = purchase_merch(
                    user=users[index], items={size.pk: quantity}, outcome='success',
                    idempotency_key=f'stock-race-{index:04}',
                )
            except Exception as exc:
                outcomes[index] = exc
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(buyers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        self.assertFalse(any(thread.is_alive() for thread in threads), 'a buyer thread hung')
        return outcomes

    def assert_exactly(self, size, outcomes, winners, starting_stock, each=1):
        refused = [o for o in outcomes if isinstance(o, OutOfStock)]
        won = [o for o in outcomes if not isinstance(o, Exception)]
        unexpected = [o for o in outcomes if isinstance(o, Exception) and not isinstance(o, OutOfStock)]
        self.assertEqual(unexpected, [])
        self.assertEqual((len(won), len(refused)), (winners, len(outcomes) - winners))

        size.refresh_from_db()
        self.assertEqual(size.stock, starting_stock - winners * each)
        self.assertGreaterEqual(size.stock, 0)
        self.assertEqual(StockMovement.objects.filter(reason='order').count(), winners)
        self.assertEqual(stock.stock_mismatches(), [])
        # Losers leave nothing behind.
        self.assertEqual(Order.objects.count(), winners)
        self.assertEqual(Payment.objects.count(), winners)
        self.assertEqual(LedgerEntry.objects.count(), winners)
        self.assertEqual(account_balance('4200'), winners * each * size.product.base_price)

    def test_two_buyers_for_the_last_hoodie(self):
        size = size_of(make_product(stock_by_size={'M': 1}), 'M')
        self.assert_exactly(size, self.race(size, buyers=2), winners=1, starting_stock=1)

    def test_twelve_buyers_for_three_hoodies(self):
        size = size_of(make_product(stock_by_size={'M': 3}), 'M')
        self.assert_exactly(size, self.race(size, buyers=12), winners=3, starting_stock=3)

    def test_buyers_of_two_each_when_three_remain(self):
        size = size_of(make_product(stock_by_size={'M': 3}), 'M')
        self.assert_exactly(size, self.race(size, buyers=6, quantity=2), winners=1, starting_stock=3, each=2)
