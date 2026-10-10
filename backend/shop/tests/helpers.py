from django.contrib.auth import get_user_model

from shop import stock
from shop.models import Product, ProductSize

User = get_user_model()


def make_product(name='Hoodie', base_price=120000, stock_by_size=None, **extra):
    """A product with all four sizes, stocked through the real restock
    function so every unit has a StockMovement behind it.
    """
    product = Product.objects.create(name=name, base_price=base_price, **extra)
    stocker, _ = User.objects.get_or_create(
        email='stocker@example.com', defaults={'name': 'Stocker', 'college_id': 'SSA-STOCK'},
    )
    for size in ['S', 'M', 'L', 'XL']:
        row = ProductSize.objects.create(product=product, size=size)
        quantity = (stock_by_size or {}).get(size, 0)
        if quantity:
            stock.restock(product_size=row, quantity=quantity, actor=stocker)
    return product


def size_of(product, size):
    return ProductSize.objects.get(product=product, size=size)
