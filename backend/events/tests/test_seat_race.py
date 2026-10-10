import threading

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase

from events.models import Ticket
from events.tests.helpers import make_event, make_tier
from events.tickets import SoldOut
from finance.models import LedgerEntry
from finance.services import account_balance
from shop.models import Order, Payment
from shop.payments import purchase_tickets

User = get_user_model()


class LastSeatRaceTests(TransactionTestCase):
    """Plan: "Two requests buy the last seat at once; exactly one succeeds,
    one gets a clear 'sold out' error."

    Each buyer runs in its own thread with its own database connection and
    its own committed transaction, released together by a barrier.
    """

    serialized_rollback = True

    def setUp(self):
        self.event = make_event()

    def race(self, tier, buyers, quantity=1):
        users = [
            User.objects.create_user(
                email=f'buyer{n}@example.com', password='correct-horse-battery',
                name=f'Buyer {n}', college_id=f'SSA-{n}',
            )
            for n in range(buyers)
        ]
        barrier = threading.Barrier(buyers)
        outcomes = [None] * buyers

        def worker(index):
            try:
                barrier.wait(timeout=10)
                outcomes[index] = purchase_tickets(
                    user=users[index], tier_id=tier.id, quantity=quantity,
                    outcome='success', idempotency_key=f'race-key-{index:04}',
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

    def assert_exactly(self, tier, outcomes, winners, seats_each=1):
        sold_out = [o for o in outcomes if isinstance(o, SoldOut)]
        won = [o for o in outcomes if not isinstance(o, Exception)]
        unexpected = [o for o in outcomes if isinstance(o, Exception) and not isinstance(o, SoldOut)]
        self.assertEqual(unexpected, [])
        self.assertEqual((len(won), len(sold_out)), (winners, len(outcomes) - winners))

        tier.refresh_from_db()
        seats = winners * seats_each
        self.assertEqual(tier.sold_count, seats)
        self.assertLessEqual(tier.sold_count, tier.capacity)
        self.assertEqual(Ticket.objects.count(), seats)
        # Losers leave nothing behind: no order, payment or ledger entry.
        self.assertEqual(Order.objects.count(), winners)
        self.assertEqual(Payment.objects.count(), winners)
        self.assertEqual(LedgerEntry.objects.count(), winners)
        self.assertEqual(account_balance('4100'), seats * tier.public_price)
        self.assertEqual(account_balance('1000'), seats * tier.public_price)

    def test_two_buyers_for_the_last_seat(self):
        tier = make_tier(self.event, capacity=1)
        self.assert_exactly(tier, self.race(tier, buyers=2), winners=1)

    def test_twelve_buyers_for_three_seats(self):
        tier = make_tier(self.event, capacity=3)
        self.assert_exactly(tier, self.race(tier, buyers=12), winners=3)

    def test_buyers_of_two_seats_each_when_three_remain(self):
        tier = make_tier(self.event, capacity=3)
        self.assert_exactly(tier, self.race(tier, buyers=6, quantity=2), winners=1, seats_each=2)
