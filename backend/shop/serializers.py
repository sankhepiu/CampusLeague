from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail

from common.validation import MAX_AMOUNT, MAX_DESCRIPTION

from .models import Coupon, Order, OrderLine, Payment, Product, ProductSize
from .payments import merch_unit_price

SIZE_ORDER = ['S', 'M', 'L', 'XL', 'ONE']
CLOTHING_SIZES = ['S', 'M', 'L', 'XL']
OUTCOME_CHOICES = ['success', 'failure', 'pending']
# ASSUMPTIONS (plan is silent): limits on one merch order.
MAX_QTY_PER_ITEM = 10
MAX_ITEMS_PER_ORDER = 20


# Everything OrderLineSerializer.get_label reads. Views that list many orders
# prefetch lines with these joins, so labels cost no extra queries.
ORDER_LINE_LABEL_RELATIONS = ('plan', 'tier__event', 'product_size__product')


class OrderLineSerializer(serializers.ModelSerializer):
    # What was bought, in words, so the client need not look up the ids.
    label = serializers.SerializerMethodField()

    class Meta:
        model = OrderLine
        fields = [
            'id', 'kind', 'label', 'plan', 'tier', 'product_size', 'qty', 'unit_price', 'discount', 'coupon_discount',
        ]
        read_only_fields = fields

    def get_label(self, line):
        if line.kind == OrderLine.Kind.MEMBERSHIP:
            return f'{line.plan.name} membership'
        if line.kind == OrderLine.Kind.TICKET:
            return f'{line.tier.event.title} · {line.tier.name}'
        return f'{line.product_size.product.name} · {line.product_size.size}'


class OrderSerializer(serializers.ModelSerializer):
    lines = OrderLineSerializer(many=True, read_only=True)
    # The coupon's code, or null. `coupon_discount` is the part of
    # `discount` that came from it.
    coupon = serializers.SlugRelatedField(slug_field='code', read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'status', 'subtotal', 'discount', 'coupon', 'coupon_discount', 'total', 'payment_ref',
            'needs_refund', 'created_at', 'lines',
        ]
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
    per item now: base_price less the sale, less their plan's merch
    discount, if any.
    """

    price = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    sizes = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description', 'category', 'base_price', 'sale_pct', 'price', 'image_url', 'active',
            'pickup_location', 'sizes',
        ]
        read_only_fields = fields

    def get_image_url(self, product):
        # Relative (/media/products/...), like receipt_url, so the frontend
        # loads it through its own /media proxy. Null when there is no image.
        return product.image.url if product.image else None

    def get_price(self, product):
        return merch_unit_price(product, self.context.get('merch_discount_pct', 0))

    def get_sizes(self, product):
        sizes = sorted(product.sizes.all(), key=lambda size: SIZE_ORDER.index(size.size))
        return ProductSizeSerializer(sizes, many=True).data


class ProductWriteSerializer(serializers.ModelSerializer):
    name = serializers.CharField(max_length=100)
    description = serializers.CharField(max_length=MAX_DESCRIPTION, allow_blank=True, required=False)
    base_price = serializers.IntegerField(min_value=1, max_value=MAX_AMOUNT)
    sale_pct = serializers.IntegerField(min_value=0, max_value=90, required=False)
    pickup_location = serializers.CharField(max_length=200, required=False)
    # Create only: false for a product that does not come in sizes.
    sized = serializers.BooleanField(required=False, default=True, write_only=True)

    class Meta:
        model = Product
        # No stock here: stock only changes through restock or a sale, so
        # every unit is explained by a StockMovement.
        fields = ['name', 'description', 'category', 'base_price', 'sale_pct', 'active', 'pickup_location', 'sized']

    def validate_name(self, value):
        taken = Product.objects.filter(name__iexact=value)
        if self.instance:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise serializers.ValidationError(ErrorDetail('A product with this name already exists.', code='unique'))
        return value

    def create(self, validated_data):
        sized = validated_data.pop('sized', True)
        product = super().create(validated_data)
        # ASSUMPTION: a sized product comes in the plan's four sizes; any
        # other product has the single size "ONE". All start at zero stock.
        sizes = CLOTHING_SIZES if sized else ['ONE']
        ProductSize.objects.bulk_create(ProductSize(product=product, size=size) for size in sizes)
        return product

    def update(self, instance, validated_data):
        # The sizes of an existing product are fixed.
        validated_data.pop('sized', None)
        return super().update(instance, validated_data)


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
    coupon = serializers.CharField(max_length=20, required=False, allow_blank=True, default='')

    def validate_items(self, items):
        ids = [item['product_size'] for item in items]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError(
                ErrorDetail('Each size may appear once; use quantity for more.', code='duplicate_item')
            )
        return items


# Razorpay (see razorpay.py) -----------------------------------------------

class RazorpayOrderSerializer(serializers.Serializer):
    """Body of POST /payments/razorpay/order: `purpose`, plus the same fields
    the mock purchase endpoint for that purpose takes. test_outcome, if sent,
    is ignored: Razorpay decides the outcome.
    """

    PURPOSES = ['membership', 'tickets', 'merch']

    purpose = serializers.ChoiceField(choices=PURPOSES)
    coupon = serializers.CharField(max_length=20, required=False, allow_blank=True, default='')

    def validate(self, attrs):
        # Imported here: members and events import this module's app.
        from events.serializers import MAX_TICKETS_PER_ORDER
        from members.models import MembershipPlan

        class Membership(serializers.Serializer):
            plan = serializers.PrimaryKeyRelatedField(queryset=MembershipPlan.objects.filter(active=True))

        class Tickets(serializers.Serializer):
            # The mock endpoint has the event in its URL; here it is
            # optional and, if sent, must be the tier's event.
            event = serializers.IntegerField(min_value=1, required=False)
            tier = serializers.IntegerField(min_value=1)
            quantity = serializers.IntegerField(min_value=1, max_value=MAX_TICKETS_PER_ORDER, default=1)

        class Merch(MerchOrderSerializer):
            test_outcome = None
            coupon = None

        by_purpose = {'membership': Membership, 'tickets': Tickets, 'merch': Merch}
        fields = by_purpose[attrs['purpose']](data=self.initial_data)
        fields.is_valid(raise_exception=True)
        return {**attrs, **fields.validated_data}


class RazorpayVerifySerializer(serializers.Serializer):
    order_id = serializers.IntegerField(min_value=1)
    razorpay_order_id = serializers.CharField(max_length=64)
    razorpay_payment_id = serializers.CharField(max_length=64)
    razorpay_signature = serializers.CharField(max_length=128)


class RazorpayCancelSerializer(serializers.Serializer):
    order_id = serializers.IntegerField(min_value=1)


# Coupons (see coupons.py) -------------------------------------------------

class CouponSerializer(serializers.ModelSerializer):
    """A coupon as the president and treasurer manage it."""

    code = serializers.RegexField(
        r'^[A-Za-z0-9_-]{3,20}$',
        error_messages={'invalid': 'Use 3 to 20 letters, digits, "-" or "_".'},
    )
    value = serializers.IntegerField(min_value=1, max_value=MAX_AMOUNT)
    min_order = serializers.IntegerField(min_value=0, max_value=MAX_AMOUNT, required=False)
    max_discount = serializers.IntegerField(min_value=1, max_value=MAX_AMOUNT, required=False, allow_null=True)
    usage_limit = serializers.IntegerField(min_value=1, max_value=1_000_000, required=False, allow_null=True)
    per_user_limit = serializers.IntegerField(min_value=1, max_value=1000, required=False)

    class Meta:
        model = Coupon
        fields = [
            'id', 'code', 'kind', 'value', 'min_order', 'max_discount', 'valid_from', 'valid_to',
            'usage_limit', 'per_user_limit', 'applies_to', 'active', 'used_count', 'created_at',
        ]
        read_only_fields = ['id', 'used_count', 'created_at']

    def validate_code(self, value):
        # Stored in upper case, so the unique check ignores letter case.
        value = value.upper()
        taken = Coupon.objects.filter(code=value)
        if self.instance:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise serializers.ValidationError(ErrorDetail('A coupon with this code already exists.', code='unique'))
        return value

    def validate(self, attrs):
        def current(name):
            return attrs.get(name, getattr(self.instance, name, None))

        if current('kind') == Coupon.Kind.PERCENT and current('value') > 100:
            raise serializers.ValidationError(
                {'value': [ErrorDetail('A percentage coupon is 1 to 100.', code='max_value')]}
            )
        starts, ends = current('valid_from'), current('valid_to')
        if starts and ends and ends <= starts:
            raise serializers.ValidationError(
                {'valid_to': [ErrorDetail('The coupon must end after it starts.', code='ends_before_start')]}
            )
        limit = current('usage_limit')
        if self.instance and limit is not None and limit < self.instance.used_count:
            raise serializers.ValidationError({'usage_limit': [ErrorDetail(
                f'This coupon has already been used {self.instance.used_count} times.', code='below_used_count',
            )]})
        return attrs


class CouponValidateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=20)
    applies_to = serializers.ChoiceField(choices=['merch', 'tickets', 'membership'])
    # What the purchase costs before the coupon, in paise.
    amount = serializers.IntegerField(min_value=1, max_value=MAX_AMOUNT)
