from rest_framework import serializers

from .models import Order, OrderLine, Payment


class OrderLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderLine
        fields = ['id', 'kind', 'plan', 'tier', 'qty', 'unit_price']
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
