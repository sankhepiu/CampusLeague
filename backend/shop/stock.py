"""Every change to ProductSize.stock happens here, together with the
StockMovement that explains it.
"""
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from audit import services as audit

from .models import ProductSize, StockMovement


class OutOfStock(Exception):
    def __init__(self, product_size):
        self.product_size = product_size
        super().__init__(f'Not enough stock for {product_size}.')


def take_stock(line):
    """Remove a paid merch line's quantity from stock. Runs inside the
    purchase transaction, which already holds a row lock on the size.

    Plan, overselling stock: "In one transaction: lock the size row, check
    stock is enough, decrement, write a StockMovement."
    """
    # Conditional update: the WHERE clause re-checks stock in the same
    # statement that takes it, so this is safe even without the lock.
    taken = ProductSize.objects.filter(pk=line.product_size_id, stock__gte=line.qty).update(
        stock=F('stock') - line.qty, updated_at=timezone.now(),
    )
    if not taken:
        raise OutOfStock(line.product_size)
    StockMovement.objects.create(
        product_size_id=line.product_size_id, delta=-line.qty,
        reason=StockMovement.Reason.ORDER, order_line=line,
    )


@transaction.atomic
def restock(*, product_size, quantity, actor):
    """Add stock. Plan: stock adjustments write an audit-log row."""
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        raise ValueError('Restock quantity must be a positive whole number.')
    size = ProductSize.objects.select_for_update().get(pk=product_size.pk)
    before = size.stock
    size.stock = before + quantity
    size.save(update_fields=['stock', 'updated_at'])
    StockMovement.objects.create(product_size=size, delta=quantity, reason=StockMovement.Reason.RESTOCK)
    audit.record(
        actor=actor, action='stock.restocked', obj=size,
        before={'stock': before}, after={'stock': size.stock, 'added': quantity},
    )
    return size


def stock_mismatches():
    """Sizes whose stock differs from the sum of their movements. Should
    always be empty; part of the reconciliation checks.
    """
    sizes = ProductSize.objects.annotate(moved=Sum('movements__delta', default=0))
    return list(sizes.exclude(stock=F('moved')))
