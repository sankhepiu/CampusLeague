"""The Razorpay endpoints. ASSUMPTION: all beyond the backend plan."""
from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import APIException, ErrorDetail, NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from events.models import TicketTier
from events.serializers import TicketSerializer
from events.tickets import SoldOut
from events.views import SalesClosedError, SoldOutError, visible_events
from members.serializers import MembershipSerializer

from . import razorpay
from .api import IdempotencyKeyReused, idempotency_key
from .models import OrderLine
from .payments import (
    IdempotencyConflict, ProductUnavailable, SalesClosed, membership_basket, merch_basket, tickets_basket,
)
from .serializers import (
    ORDER_LINE_LABEL_RELATIONS, OrderLineSerializer, OrderSerializer, PaymentSerializer,
    RazorpayCancelSerializer, RazorpayOrderSerializer, RazorpayVerifySerializer,
)
from .stock import OutOfStock
from .views import OutOfStockError, ProductUnavailableError


class GatewayNotEnabledError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = 'Razorpay is not enabled on this server. Use the standard purchase endpoints.'
    default_code = 'gateway_not_enabled'


class GatewayUnavailableError(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = 'The payment gateway could not be reached. You have not been charged. Please try again.'
    default_code = 'gateway_unavailable'


class AmountTooSmallError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'This total is below the minimum the payment gateway accepts (1 rupee).'
    default_code = 'amount_too_small'


class InvalidSignatureError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'The payment could not be verified.'
    default_code = 'invalid_signature'


class OrderAlreadyPaidError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = 'This order has already been paid.'
    default_code = 'order_already_paid'


class SoldOutAfterPaymentError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = (
        'Sold out while you were paying. Nothing was issued and your payment has been flagged for a refund.'
    )
    default_code = 'sold_out'


def basket_for(request, data):
    """The basket (see payments.py) for a validated request body."""
    user = request.user
    if data['purpose'] == 'membership':
        return membership_basket(user=user, plan=data['plan'])
    if data['purpose'] == 'merch':
        return merch_basket(user=user, items={item['product_size']: item['quantity'] for item in data['items']})

    # Tickets: the same checks the mock endpoint makes from its URL. A tier
    # of a draft event is reported like a tier that does not exist.
    tier = TicketTier.objects.filter(pk=data['tier'], event__in=visible_events(request)).first()
    if tier is None or data.get('event', tier.event_id) != tier.event_id:
        raise ValidationError({'tier': [ErrorDetail('This event has no such tier.', code='does_not_exist')]})
    return tickets_basket(user=user, tier_id=tier.pk, quantity=data['quantity'])


def checkout_description(order):
    """What Razorpay's checkout shows under the club's name."""
    lines = order.lines.select_related(*ORDER_LINE_LABEL_RELATIONS).order_by('id')
    parts = []
    for line in lines:
        label = OrderLineSerializer().get_label(line)
        parts.append(label if line.kind == OrderLine.Kind.MEMBERSHIP else f'{label} x{line.qty}')
    return ', '.join(parts)[:255]


def purchase_body(result):
    """The same body the mock purchase endpoint for this kind returns."""
    body = {
        'order': OrderSerializer(result.order).data,
        'payment': PaymentSerializer(result.payment).data,
    }
    kind = result.order.lines.all()[0].kind
    if kind == OrderLine.Kind.MEMBERSHIP:
        body['membership'] = MembershipSerializer(result.membership).data
    elif kind == OrderLine.Kind.TICKET:
        body['tickets'] = TicketSerializer(result.tickets, many=True).data
    return body


class RazorpayView(APIView):
    """Turns the service's exceptions into this API's error responses."""

    permission_classes = [IsAuthenticated]

    def handle_exception(self, exc):
        errors = {
            razorpay.GatewayNotEnabled: GatewayNotEnabledError,
            razorpay.GatewayUnavailable: GatewayUnavailableError,
            razorpay.AmountTooSmall: AmountTooSmallError,
            razorpay.OrderNotFound: NotFound,
            razorpay.InvalidSignature: InvalidSignatureError,
            razorpay.OrderAlreadyPaid: OrderAlreadyPaidError,
            razorpay.SoldOutAfterPayment: SoldOutAfterPaymentError,
            IdempotencyConflict: IdempotencyKeyReused,
            SoldOut: SoldOutError,
            SalesClosed: SalesClosedError,
            ProductUnavailable: ProductUnavailableError,
        }
        if isinstance(exc, OutOfStock):
            size = exc.product_size
            exc = OutOfStockError(f'Out of stock: {size.product.name} size {size.size} has {size.stock} left.')
        elif type(exc) in errors:
            exc = errors[type(exc)]()
        return super().handle_exception(exc)


class PaymentConfigView(APIView):
    """GET /payments/config. Which gateway the frontend should use."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        gateway = razorpay.active_gateway()
        return Response({
            'gateway': gateway,
            # The key id is public (the browser needs it to open the
            # checkout). The key secret is never sent anywhere but Razorpay.
            'key_id': settings.RAZORPAY_KEY_ID if gateway == razorpay.RAZORPAY else None,
        })


class RazorpayOrderView(RazorpayView):
    """POST /payments/razorpay/order. Any logged-in user."""

    def post(self, request):
        key = idempotency_key(request)
        serializer = RazorpayOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order, created = razorpay.start_checkout(
            # Buyer from the token; prices and discount from the server.
            user=request.user, idempotency_key=key, **basket_for(request, serializer.validated_data),
        )
        body = {
            'order_id': order.pk,
            'razorpay_order_id': order.razorpay_order_id,
            # Razorpay's public key id, under the name its checkout uses.
            'key': settings.RAZORPAY_KEY_ID,
            'amount': order.total,
            'currency': razorpay.CURRENCY,
            'name': razorpay.MERCHANT_NAME,
            'description': checkout_description(order),
            'prefill': {'name': request.user.name, 'email': request.user.email},
        }
        return Response(body, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class RazorpayVerifyView(RazorpayView):
    """POST /payments/razorpay/verify. The buyer of the order only."""

    def post(self, request):
        serializer = RazorpayVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = razorpay.verify_payment(
            user=request.user, order_id=data['order_id'],
            razorpay_order_id=data['razorpay_order_id'],
            razorpay_payment_id=data['razorpay_payment_id'],
            signature=data['razorpay_signature'],
        )
        return Response(
            purchase_body(result), status=status.HTTP_200_OK if result.replayed else status.HTTP_201_CREATED,
        )


class RazorpayCancelView(RazorpayView):
    """POST /payments/razorpay/cancel. The buyer of the order only."""

    def post(self, request):
        serializer = RazorpayCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = razorpay.cancel_checkout(user=request.user, order_id=serializer.validated_data['order_id'])
        return Response({'order': OrderSerializer(order).data})
