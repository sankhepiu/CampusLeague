from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail

from .models import Order, OrderLine, Payment, Product, ProductSize

SIZE_ORDER = ['S', 'M', 'L', 'XL']
OUTCOME_CHOICES = ['success', 'failure', 'pending']
# ASSUMPTIONS (plan is silent): limits on one merch order.
MAX_QTY_PER_ITEM = 10
MAX_ITEMS_PER_ORDER = 20


class OrderLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderLine
        fields = ['id', 'kind', 'plan', 'tier', 'product_size', 'qty', 'unit_price', 'discount']
        read_only_fields = fields


class OrderSerializer(serializers.ModelSerializer):
    lines = OrderLineSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'status', 'subtotal', 'discount', 'total', 'payment_ref', 'created_at', 'lines']
        read_only_fields = fields


class PaymentSerializer(serializers.ModelSerializer):
    # The idempotency key is deliberately not returned.
    class Meta:
        model = Payment
        fields = ['id', 'amount', 'status', 'gateway_ref', 'created_at']
        read_only_fields = fields


class ProductSizeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductSize
        fields = ['id', 'size', 'stock']
        read_only_fields = fields


class ProductSerializer(serializers.ModelSerializer):
    """A product as shoppers see it. `price` is what the caller would pay
    per item now: base_price less their plan's merch discount, if any.
    """

    price = serializers.SerializerMethodField()
    sizes = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ['id', 'name', 'description', 'base_price', 'price', 'image', 'active', 'sizes']
        read_only_fields = fields

    def get_price(self, product):
        pct = self.context.get('merch_discount_pct', 0)
        return product.base_price - product.base_price * pct // 100

    def get_sizes(self, product):
        sizes = sorted(product.sizes.all(), key=lambda size: SIZE_ORDER.index(size.size))
        return ProductSizeSerializer(sizes, many=True).data


class ProductWriteSerializer(serializers.ModelSerializer):
    base_price = serializers.IntegerField(min_value=1)

    class Meta:
        model = Product
        # No stock here: stock only changes through restock or a sale, so
        # every unit is explained by a StockMovement.
        fields = ['name', 'description', 'base_price', 'image', 'active']

    def create(self, validated_data):
        product = super().create(validated_data)
        # ASSUMPTION: every product comes in the plan's four sizes, each
        # starting at zero stock.
        ProductSize.objects.bulk_create(ProductSize(product=product, size=size) for size in SIZE_ORDER)
        return product


class RestockSerializer(serializers.Serializer):
    size = serializers.ChoiceField(choices=SIZE_ORDER)
    quantity = serializers.IntegerField(min_value=1, max_value=10000)


class MerchItemSerializer(serializers.Serializer):
    product_size = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1, max_value=MAX_QTY_PER_ITEM, default=1)


class MerchOrderSerializer(serializers.Serializer):
    # No price, discount, total or user field: all come from the server.
    items = MerchItemSerializer(many=True, allow_empty=False, max_length=MAX_ITEMS_PER_ORDER)
    test_outcome = serializers.ChoiceField(choices=OUTCOME_CHOICES, default='success')

    def validate_items(self, items):
        ids = [item['product_size'] for item in items]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError(
                ErrorDetail('Each size may appear once; use quantity for more.', code='duplicate_item')
            )
        return items
